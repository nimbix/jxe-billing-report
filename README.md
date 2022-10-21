# jxe-billing-report
Billing report cron to pull JXE compute and storage costs into a single emailed report. The report depends on a Billingcode tag/label and vault name tag/label that will need to be added to the AWS EFS/GCP Filestore. 

## GCP storage setup

To enable the GCP storage code you can set the environment variable "GCP_STORAGE" to true. 

GCP requires an export of billing information to BigQuery to be able to query it. The following link from Google explains the process.

https://cloud.google.com/billing/docs/how-to/export-data-bigquery-setup

Additionally the report depends on a json authentication key that has access to connect and read your BigQuery billing data. It is recommended that you create a Service Account with access to BigQuery to generate your authentication key. The following link explains GCP service account keys.

https://cloud.google.com/iam/docs/creating-managing-service-account-keys

## AWS storage setup

To enable the AWS storage code you can set the environment variable "AWS_STORAGE" to true.

AWS allows cost and usage data to be pulled using the aws commandline tool. The report depends on a secret that contains the AWS credentials you want to use to pull EFS storage cost data.

To create that secret you can run the following command pointing  --from-file to the folder containing your AWS credentials file usually ~/.aws.

<pre><code>kubectl create secret generic awscreds --from-file=aws -n jarvice-system</pre></code>

## Extendability
The python script generating the billing report is extendable. The dinit() function defines the dictionary used to send the report. To add a new storage cost category the code needs to ingest the existing totals dictionary and return it with the updated costs.
```
def dinit(bc, c=[], com=0, stor=0, v=[], gv=[]):
    return { "company" : c.copy(), "BillingCode" : str(bc), "compute" : com, "storage" : stor, "awsvaults": v.copy(), "gcpvaults": gv.copy()}
```

The new storage function will need to take the date format '%Y-%m-%d'. The current code calculates first of this month and first of next month for the month requested. 

The totals dictionary uses the the billing code as the key for the dictionary defined in the dinit() function above. Your storage function will need to add to the storage cost column and optionally append to a list of vault names. Example of adding to the storage costs total for a billing code and appending the vault names.
```
            totals[bc]["awsvaults"].append(vaultname)
            totals[bc]["storage"] += float(met["Metrics"]['BlendedCost']['Amount'])
    return totals
```

## Helm
To install this cron via helm you can run the following command. Acceptable values for billingperiod are "last", "current" and year month date format. 202209 for example. Current refers to billing data from this month and last refers to billing data from the previous month. The AWS/GCP storage portions can be enabled or disabled as needed. 

```
helm install billing-report-lastmonth helm/. --values - <<EOF
report:
    image: "us-docker.pkg.dev/jarvice/images/jxe-billing-report:20221021"
    name: "billing-report-lastmonth"
    #Billing Code tag name applied to the EFS vaults
    bctag: "BillingCode"
    #Name tag applied to the EFS vaults
    nametag: "Name"
    #Email list separated by a : For example "email1@email.com:email2@email.com"
    emaillist: "mark.mankiewicz@nimbix.net"
    fromemail: "user@nimbix.net"
    #Email server with port included example: "smtp.sendgrid.net:587"
    emailserver: ""
    emailserveruser: ""
    emailserverpassword: ""
    cronschedule: "0 9 1 * *"
    billingperiod: "last"
    awsstorage:
        enabled: true
        awscredsecret: "awscreds"
        bctag: "BillingCode"
        nametag: "Name"
    gcpstorage:
        enabled: true
        bigquerydb: ""
        gcpcredsecret: "gcpcreds"
        gcpcredfilename: "nimbix-billing.json"
        bclabel: "billing-code"
        namelabel: "name"

EOF
```

To run a test cronjob you can create a job from your newly created cronjob.
```
kubectl create job billing-test-job-01 --from=cronjobs/billing-report-last-month -n jarvice-system
```
## Environment Variables
```
  - name: AWS_STORAGE
    value: 'Enable AWS storage code by setting to true'
  - name: BC_TAG
    value: 'AWS billing code tag'
  - name: NAME_TAG
    value: 'AWS vault name tag'
  - name: GCP_STORAGE
    value: 'Enable GCP storage code by setting to true'
  - name: GOOGLE_APPLICATION_CREDENTIALS
    value: 'Google json access key location'
  - name: BQ_DB
    value: 'BigQuery database name'
  - name: BC_LABEL
    value: 'GCP billing code label'
  - name: NAME_LABEL
    value: 'GCP vault name label'
  - name: EMAIL_SERVER
    value: 'Email server with port'
  - name: EMAIL_SERVER_USER
    value: 'Email server user'
  - name: EMAIL_SERVER_PASSWORD
    value: 'Email server password'
  - name: FROM_EMAIL
    value: 'Email address to send mail from'
  - name: EMAIL_LIST
    value: 'user1@email.com:user2@email.com:user3@email.com...'
```
