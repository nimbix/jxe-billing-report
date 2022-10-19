# jxe-billing-report
Billing report cron to pull JXE compute and AWS EFS Storage costs into a single emailed report.


You will need to create a secret that contains the AWS credentials you want to use to pull EFS storage cost data.
To create that secret you can run the following command pointing  --from-file to the folder containing your AWS credentials file usually ~/.aws.

<pre><code>kubectl create secret generic awscreds --from-file=aws -n jarvice-system</pre></code>

To install this cron via helm you can run the following command. Acceptable values for billingperiod are "last", "current" and year month date format. 202209 for example. Current refers to billing data from this month and last refers to billing data from the previous month.

```
helm install billing-report-lastmonth helm/. --values - <<EOF
report:
    image: "us-docker.pkg.dev/jarvice/images/jxe-billing-report:20221020"
    name: "billing-report-lastmonth"
    #Billing Code tag name applied to the EFS vaults
    bctag: "BillingCode"
    #Name tag applied to the EFS vaults
    nametag: "Name"
    #Email list separated by a : For example "email1@email.com:email2@email.com"
    emaillist: "user1@nimbix.net:user2@nimbix.net"
    fromemail: "user@nimbix.net"
    #Email server with port included example: "smtp.sendgrid.net:587"
    emailserver: "email.server"
    emailserveruser: "email_user"
    emailserverpassword: "email_pw"
    awscredsecret: "awscreds"
    cronschedule: "0 9 1 * *"
    billingperiod: "last"
EOF 
```

To run a test cronjob you can create a job from your newly created cronjob.
```
kubectl create job billing-test-job-01 --from=cronjobs/billing-report-last-month -n jarvice-system
```
