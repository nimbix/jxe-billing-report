#!/usr/bin/python
import sys
import getopt
import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email import encoders
from email.message import Message
from email.mime.audio import MIMEAudio
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.text import MIMEText

def send_email(emailfrom, emailto, subject, body, fileToSend="" ):
    msg = MIMEMultipart()
    html = ""
    text = str(body)
    body = MIMEMultipart()
    body.attach(MIMEText(text, 'plain'))
    msg = MIMEMultipart()
    msg.preamble = 'This is a multi-part message in MIME format.\n'
    msg.epilogue = ''
    msg["From"] = emailfrom
    msg["To"] = emailto
    msg["Subject"] = subject
    msg.attach(body)
    if fileToSend:
        fp = open(fileToSend, "rb")
        attachment = MIMEBase('application','csv')
        attachment.set_payload(fp.read())
        subtype = 'octet-stream'
        fp.close()
        encoders.encode_base64(attachment)
        attachment.add_header("Content-Disposition", "attachment", filename=fileToSend)
        msg.attach(attachment)
        attachment = Message()
    user = os.environ["EMAIL_SERVER_USER"]
    password = os.environ["EMAIL_SERVER_PASSWORD"]
    server = smtplib.SMTP(os.environ["EMAIL_SERVER"])
    server.ehlo()
    server.starttls()
    server.login(user, password)
    server.sendmail(emailfrom, emailto, msg.as_string())
    server.quit()


def main(argv):
    email_from = ""
    email_to = ""
    subject = ""
    body = ""
    att = ""
    try:
        opts, args = getopt.getopt(argv,"hf:t:s:b:a:")
    except getopt.GetoptError:
        print ('send_email.py -f \'from@email.com\' -t \'to@email.com\' -s \'Subject\' -a\'File to attach\' -b \'Body of email\'')
        sys.exit(2)
    for opt, arg in opts:
        if opt == '-h':
            print ('send_email.py -f \'from@email.com\' -t \'to@email.com\' -s \'Subject\' -a\'File to attach\' -b \'Body of email\'')
            sys.exit()
        elif opt in ("-f"):
            email_from = arg
        elif opt in ("-t"):
            email_to = arg
        elif opt in ("-s"):
            subject = arg
        elif opt in ("-b"):
            body = arg
        elif opt in ("-a"):
            att = arg
    send_email(email_from, email_to, subject, body, att)

if __name__ == "__main__":
   main(sys.argv[1:])
