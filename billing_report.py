#!/usr/bin/env python
import boto3
import time
import datetime
import calendar
import sys
import csv
import os
import re
import mysql.connector
from collections import OrderedDict
from kubernetes import config
from kubernetes.client.api import core_v1_api
from pod_exec import exec_command, get_pod_name
from send_email import send_email #Configure for your email server
from google.cloud import bigquery


def db_conn():
    db_pw = os.environ['MYSQL_PW']
    db_user = os.environ['MYSQL_USER']
    db = os.environ['MYSQL_DB']
    db_host = os.environ['MYSQL_HOST']
    dbcnx = mysql.connector.connect(user=db_user, password=db_pw,
                                  host=db_host,
                                  database=db,
                                  port='3306')
    dbcursor = dbcnx.cursor()
    return dbcnx, dbcursor

def get_aws_cost_and_usage(timeperiod, granularity, costfilter, metrics, groupby):
    client = boto3.client('ce')
    token = "first"
    results = []
    while token :
        if token != "first":
            kwargs = {"NextPageToken": token}
        else:
            kwargs = {}
        response = client.get_cost_and_usage(TimePeriod = timeperiod,Granularity = 'MONTHLY',Filter = costfilter, Metrics = metrics,GroupBy = groupby, **kwargs )
        results += response["ResultsByTime"]
        token = response.get("NextPageToken")
    return results

def run_dal_cmd(cmd, namespace):
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config("/app/kubeconfig")
    core_v1 = core_v1_api.CoreV1Api()
    dalHost = get_pod_name(core_v1, 'jarvice-system','jarvice-dal-.*-.....')
    commands = [ 'python3', '-c', cmd ]
    results = eval(exec_command(core_v1, dalHost, namespace, commands ))
    return results

def dinit(bc, c=[], com=0, stor=0, v=[], gv=[]):
    return { "company" : c.copy(), "BillingCode" : str(bc), "compute" : com, "storage" : stor, "awsvaults": v.copy(), "gcpvaults": gv.copy()}

def aws_storage_cost(totals, firstofmonth, nextmonth, bctag, nametag):

    #Define AWS Cost and Usage Query
    timeperiod = {
            'Start': firstofmonth,
            'End': nextmonth
        }
    granularity = "MONTHLY"
    costfilter = {
                "Dimensions": {
            "Key": "SERVICE",
            "Values": [
                "Amazon Elastic File System",
                "AWS Backup"
            ]
        }
    }
    metrics = [
            "BlendedCost",
            "UsageQuantity",
            "NormalizedUsageAmount"
        ]
    groupby = [
            {"Type": "TAG", "Key": bctag},
            {"Type": "TAG","Key": nametag}
          ]
    results = get_aws_cost_and_usage(timeperiod, granularity, costfilter, metrics, groupby)

    #Sum up storage results by billing code
    for res in results:
        for met in res["Groups"]:
            for key in met["Keys"] :
                vaultname=""
                if key.split("$")[0] == bctag :
                    bc = key.split("$")[1]
                    if bc not in totals :
                        totals[bc] = dinit(bc = bc)
                elif key.split("$")[0] == "Name" :
                    vaultname = (key.split("$")[1])
            totals[bc]["awsvaults"].append(vaultname)
            totals[bc]["storage"] += float(met["Metrics"]['BlendedCost']['Amount'])
    return totals

def jxe_compute_cost(totals, period, firstofmonth, nextmonth):
    #Run Jarvice dal commands to get compute totals and company lists.
    if period != "range" :
        report = 'import JarviceDAL as dal; print(dal.req(\'userReportBilling\', timeperiod=\'{}\'))'.format(period)
    else :
        report = 'import JarviceDAL as dal; print(dal.req(\'userReportBilling\', timeperiod=\'{}\', startdate=\'{}\', enddate=\'{}\'))'.format(period, firstofmonth, nextmonth)
    users_cmd = 'import JarviceDAL as dal; print(dal.req(\'userList\'))'
    billing_report = run_dal_cmd(report, "jarvice-system")
    users = run_dal_cmd(users_cmd, "jarvice-system")

    #Sum up compute totals by billing code
    for key in billing_report :
        if 'billing_code' in billing_report[key] :
            #print("BC : ",billing_report[key]['billing_code'])
            #print("Compute Cost : ",billing_report[key]['compute_cost'])
            bc = str(billing_report[key]['billing_code'])
            if bc not in totals :
                totals[bc] = dinit(bc = bc)
            totals[bc]["compute"] += float(billing_report[key]['compute_cost'])
        else:
            if key not in totals :
                totals[key] = dinit(bc = key)
            totals[key]['compute'] += float(billing_report[key]['compute_cost'])

    #Drop compute summed total entry
    totals.pop("@")
    return totals

def gcp_storage_cost(totals, month):
    bqdb = os.environ["BQ_DB"]
    bc_label = os.environ["BC_LABEL"]
    name_label = os.environ["NAME_LABEL"]
    bqclient = bigquery.Client()
    query = """SELECT
      IFNULL(((select l.value from UNNEST(labels) l where key = "{}" )),"NoBillingCode") as BillingCode,
      SUM(cost) as StorageCost,
      --service.description as service,
      IFNULL(((select l.value from UNNEST(labels) l where key = "{}" )),NULL) as name,
      SUM(usage.amount_in_pricing_units) as Usage,
      ((SUM(CAST(cost * 1000000 AS int64))
            + SUM(IFNULL((SELECT SUM(CAST(c.amount * 1000000 as int64))
                          FROM UNNEST(credits) c
                          WHERE c.type not in("COMMITTED_USAGE_DISCOUNT", "PROMOTION")
                          ), 0))) / 1000000)  as cost
    FROM `{}` a
    where cost > 0.01
    AND invoice.month = '{}'
    AND service.description like "Cloud Filestore%"
    GROUP BY 1,3
    ORDER BY cost DESC""".format(bc_label, name_label, bqdb, month)
    query_job = bqclient.query(query)  # API request
    rows = query_job.result()
    for row in rows:
        bc = str(row['BillingCode'])
        if not row['name'] :
            name = ""
        else:
            name = row['name']
        if bc not in totals:
            totals[bc] = dinit(bc = bc)
        totals[bc]['storage'] += float(row['StorageCost'])
        totals[bc]['gcpvaults'].append(name)
        #totals[row['BillingCode']] = row['StorageCost']
    return totals

def main():
    today = datetime.date.today()
    first = today.replace(day=1)
    lastMonth = first - datetime.timedelta(days=1)
    bctag = os.environ["BC_TAG"]
    nametag = os.environ["NAME_TAG"]
    period = sys.argv[1]
    if period == "current":
        month = today.strftime("%Y%m")
        working_date = first
    elif period == "last" :
        month = lastMonth.strftime("%Y%m")
        working_date = lastMonth
    elif re.match('[0-9][0-9][0-9][0-9][0-9][0-9]', period) :
        month = str(period)
        period = "range"
        working_date = datetime.datetime.strptime(month, "%Y%m")
    else:
        print("There is a problem with your input.")
        print("Accepted values: last, current OR year month date string 202209 for example.")
        sys.exit(1)
    d, lastday = calendar.monthrange(int(month[0:4]), int(month[-2:].strip("0")))
    lastofmonth="{}-{}-{}".format(month[0:4],month[-2:],str(lastday))
    firstofmonth="{}-{}-{}".format(month[0:4],month[-2:],"01")
    nextmonth = (datetime.datetime.strptime(lastofmonth, '%Y-%m-%d') + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
    month_name = working_date.strftime("%B")
    year = working_date.year
    totals = {}
    if os.getenv("AWS_STORAGE") and os.environ["AWS_STORAGE"]:
        totals = aws_storage_cost(totals, firstofmonth, nextmonth, bctag, nametag)
    if os.getenv("GCP_STORAGE") and os.environ["GCP_STORAGE"]:
        totals = gcp_storage_cost(totals, month)
    totals = jxe_compute_cost(totals, period, firstofmonth, nextmonth)

    #Build dictionary using the Jarvice username as the key for payer Company lookup.
    users_cmd = 'import JarviceDAL as dal; print(dal.req(\'userList\'))'
    users = run_dal_cmd(users_cmd, "jarvice-system")
    usernames = {}
    for user in users :
        user = dict(user)
        usernames[user['user_login']] = user

    #Loop through users to get list of companies under a given billing code.
    for user in users :
        bc = str(user["billing_code"])
        if bc not in totals :
            totals[bc] = dinit(bc = bc)
        if bc in totals and user["payer"] and usernames[user["payer"]]["user_company"] and usernames[user["payer"]]["user_company"] not in totals[bc]["company"] and user["payer"] != "":
            totals[bc]["company"].append(usernames[user["payer"]]["user_company"])
        elif bc in totals and user["user_company"] and user["user_company"] not in totals[bc]["company"] :
            totals[bc]["company"].append(user["user_company"])
        elif bc in totals :
            #print("User or Payers Company is already in the list of companies for that billing code. skipping.", user)
            continue
        else:
            print("Unaccounted for user or payer company:", user)

    #Create list from dictionary for sorting
    totals_list = []
    for k, v in totals.items() :
        v["BillingCode"] = k
        totals_list.append(v)

    #Fix missing entries
    for v in totals_list :
        if "company" not in v :
            if v["BillingCode"] == "" :
                v["company"] = ["NoBillingCode"]
            else:
                v["company"] = ["Billing Code: " + v["BillingCode"]]

    #Sort list by compute total
    tl = sorted(totals_list, key=lambda d: d['compute'], reverse=True)
    report_name = "billing_report_{}_{}.csv".format(month_name, year)
    with open(report_name , 'w', newline='') as csvfile:
        cwriter = csv.writer(csvfile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
        cwriter.writerow(['Account', 'Billing Code', 'Compute Cost', 'Storage Cost', 'AWS EFS Vaults', 'GCP Filestore Vaults'])
        deleteString = """ DELETE FROM billing_report_months WHERE  Month = {};""".format(month)
        print(deleteString)
        db_cnx, db_cursor = db_conn()
        db_cursor.execute(deleteString)
        db_cnx.commit()
        for v in tl :
            cwriter.writerow([ " ".join(v["company"]), v["BillingCode"], v["compute"], v["storage"], ", ".join(v["awsvaults"]), ", ".join(v["gcpvaults"]) ])
            insertString = """ INSERT INTO billing_report_months (AccountName, BillingCode, ComputeCost, StorageCost, Month)
VALUES ('{}', '{}', '{}', '{}', '{}'); """.format(" ".join(v["company"]), v["BillingCode"], v["compute"], v["storage"], month)
            print(insertString)
            db_cursor.execute(insertString)
            db_cnx.commit()

    emails = os.environ["EMAIL_LIST"].split(":")
    from_email = os.environ["FROM_EMAIL"]
    body = "Billing report for the month of {} {}.".format(month_name, year)
    subject = "Nimbix Billing Report {} {}".format(month_name, year)
    for email in emails :
        send_email(from_email, email, subject, body, report_name)
if __name__ == "__main__":
    main()
