#!/bin/python3
from asyncio import protocols
from flask import Flask, request, render_template, jsonify, redirect, render_template, make_response, session, flash
from flask_login import LoginManager, login_required
from oauthlib.oauth2 import WebApplicationClient
import json
import jwt
import os
import subprocess
import json
import re
import copy
import requests
from functools import wraps
import time

global ORACLE_CLIENT_ID
global ORACLE_IDCS_SECRET
global ORACLE_IDCS_URL
global ADDRESS

os.environ["XTABLES_LIBDIR"] = "/usr/lib64/xtables"

def post_routing():
    post_routing = subprocess.Popen("iptables -t nat -A PREROUTING -p tcp --dport 222 -j DNAT --to-destination 10.0.22.63:22",
                                    shell=True, stdout=subprocess.PIPE).stdout.read().decode()

def pre_routing():
    pre_routing = subprocess.Popen("iptables -t nat -A POSTROUTING -p all -o ens3 -j MASQUERADE",
                                   shell=True, stdout=subprocess.PIPE).stdout.read().decode()

def flush_iptables():
    flush_routing = subprocess.Popen("iptables -t nat -F && iptables -t nat -X && iptables -F && iptables -X",
                                     shell=True, stdout=subprocess.PIPE).stdout.read().decode()

def get_nat_rules():
    nat_rules = []
    collect_nat_rules = subprocess.Popen(
        "iptables -t nat -S", shell=True, stdout=subprocess.PIPE).stdout.read()
    collect_nat_rules = collect_nat_rules.split(b'\n')
    for nat_rule in collect_nat_rules:
        if b'-A' in nat_rule:
            nat_rules.append(nat_rule)
    return (nat_rules)

def load_post_routing(data):
    flush_iptables()
    data = json.loads(data)
    for element in data:
        if data[element]['chain'] == "PREROUTING":
            prep = "iptables -t nat -A %s -p %s --dport %s -j %s --to-destination %s:%s" % (
                data[element]['chain'], data[element]['protocol'], data[element]['destination_port'], data[element]['target'], data[element]['forward_ip'], data[element]['forward_port'])
            result = subprocess.Popen(prep, shell=True, stdout=subprocess.PIPE)
            time.sleep(.3)
        elif data[element]['chain'] == "POSTROUTING":
            if data[element]['source_ip'].upper() != "NULL" and len(data[element]['source_ip']) > 0:
                prep = "iptables -t nat -A %s -p %s -o %s -j %s --to-source %s" % (
                    data[element]['chain'], data[element]['protocol'], data[element]['output_interface'], data[element]['target'].upper(), data[element]['source_ip'])
                result = subprocess.Popen(
                    prep, shell=True, stdout=subprocess.PIPE)
                time.sleep(.3)
            else:
                prep = "iptables -t nat -A %s -p %s -o %s -j %s" % (
                    data[element]['chain'], data[element]['protocol'], data[element]['output_interface'], data[element]['target'].upper())
                result = subprocess.Popen(
                    prep, shell=True, stdout=subprocess.PIPE)
                time.sleep(.3)
        print(result)
    nat_rules = get_nat_rules()
    print(nat_rules)
    return nat_rules

def process_nat_rules(nat_rules):
    di = 0
    si = 0
    dnat_dictionary_rule = {}
    snat_dictionary_rule = {}
    key_data = []
    try:
        nat_rules = json.loads(nat_rules)
    except:
        pass
    print(type(nat_rules))
    print(nat_rules)
    for nat_rule in nat_rules:
        rule_data = nat_rule.decode().split(" ")
        chain = rule_data[rule_data.index("-A")+1]
        try:
            collect = {}
            if chain == "PREROUTING":
                collect['chain'] = rule_data[rule_data.index("-A")+1]
                collect['protocol'] = rule_data[rule_data.index("-p")+1]
                collect['destination_port'] = rule_data[rule_data.index(
                    "--dport")+1]
                collect['target'] = rule_data[rule_data.index("-j")+1]
                collect['forward_ip'] = rule_data[rule_data.index(
                    "--to-destination")+1].split(":")[0]
                collect['forward_port'] = rule_data[rule_data.index(
                    "--to-destination")+1].split(":")[1]
                if len(key_data) == 0:
                    dnat_dictionary_rule[di] = collect
                    key_data.append(collect)
                    di = di+1
                else:
                    if collect not in key_data:
                        dnat_dictionary_rule[di] = collect
                        key_data.append(collect)
                        di = di+1
            elif chain == "POSTROUTING":
                collect['chain'] = rule_data[rule_data.index("-A")+1]
                try:
                    collect['protocol'] = rule_data[rule_data.index("-p")+1]
                except:
                    collect['protocol'] = "all"
                collect['target'] = rule_data[rule_data.index("-j")+1]
                collect['output_interface'] = rule_data[rule_data.index(
                    "-o")+1]
                try:
                    collect['source_ip'] = rule_data[rule_data.index(
                        "--to-source")+1]
                except:
                    collect['source_ip'] = "Null"
                if len(key_data) == 0:
                    snat_dictionary_rule[si] = collect
                    key_data.append(collect)
                    si = si+1
                else:
                    if collect not in key_data:
                        snat_dictionary_rule[si] = collect
                        key_data.append(collect)
                        si = si+1
        except:
            pass
    return dnat_dictionary_rule, snat_dictionary_rule

app = Flask(__name__, template_folder='templates')
app.secret_key = "ONA"
login_manager = LoginManager()
login_manager.init_app(app)
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# Load configuration from environment variables
ORACLE_CLIENT_ID = os.getenv("ORACLE_CLIENT_ID")
ORACLE_IDCS_SECRET = os.getenv("ORACLE_IDCS_SECRET")
ORACLE_IDCS_URL = os.getenv("ORACLE_IDCS_URL")
ADDRESS = os.getenv("ADDRESS")

client = WebApplicationClient(ORACLE_CLIENT_ID)

@login_manager.user_loader
def get_oracle_provider_cfg():
    return ORACLE_IDCS_URL

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        access_token = session.get('x-access-token')
        if not access_token:
            return make_response(redirect(ADDRESS + "/login"))
        try:
            data = jwt.decode(access_token, audience=ORACLE_IDCS_URL, options={"verify_signature": False})
            current_user = data['user_displayname']
        except Exception:
            session.pop('x-access-token', None)
            return make_response(redirect(ADDRESS + "/login"))
        return f(current_user, *args, **kwargs)
    return decorated

@app.route('/', methods=['GET', 'POST'])
@token_required
def dnoa(current_user):
    # Check for null config values
    if not all([ORACLE_CLIENT_ID, ORACLE_IDCS_SECRET, ORACLE_IDCS_URL]):
        return redirect('/setup')

    if request.method == "GET":
        nat_rules = get_nat_rules()
        nat_rules = process_nat_rules(nat_rules)
        return render_template('bootstrap_table.html', title='Oracle NAT Appliance', dnat_rules=nat_rules[0], snat_rules=nat_rules[1])
    elif request.method == "POST":
        data = request.data.decode()
        nat_rules = load_post_routing(data)
        nat_rules = process_nat_rules(nat_rules)
        flash('Submit Successful')
        return render_template('bootstrap_table.html', title='Oracle NAT Appliance', dnat_rules=nat_rules[0], snat_rules=nat_rules[1])

@app.route("/setup", methods=['GET', 'POST'])
def setup():
    if request.method == 'POST':
        # Set environment variables for this session (optional)
        os.environ["ORACLE_CLIENT_ID"] = request.form['client_id']
        os.environ["ORACLE_IDCS_SECRET"] = request.form['client_secret']
        os.environ["ORACLE_IDCS_URL"] = request.form['idcs_url']
        os.environ["ADDRESS"] = request.form['address']

        # Redirect to main page after setup
        flash('Configuration saved successfully!')
        return redirect('/')

    return render_template('setup_form.html')

@app.route("/login")
def login():
    oracle_provider_cfg = get_oracle_provider_cfg()
    authorization_endpoint = oracle_provider_cfg + '/oauth2/v1/authorize'
    client = WebApplicationClient(ORACLE_CLIENT_ID)
    request_uri = client.prepare_request_uri(
        authorization_endpoint,
        redirect_uri=request.base_url + "/callback",
        state=request.base_url,
        scope=['openid'],
    )
    return redirect(request_uri)

@app.route("/login/callback")
def callback():
    code = request.args.get("code")
    oracle_provider_cfg = get_oracle_provider_cfg()
    token_endpoint = oracle_provider_cfg + '/oauth2/v1/token'
    token_url, headers, body = client.prepare_token_request(
        token_endpoint,
        authorization_response=request.url,
        redirect_url=request.base_url,
        code=code
    )
    token_response = requests.post(
        token_url,
        headers=headers,
        data=body,
        auth=(ORACLE_CLIENT_ID, ORACLE_IDCS_SECRET),
    )
    token = client.parse_request_body_response(json.dumps(token_response.json()))
    access_token = token['access_token']
    session['x-access-token'] = access_token
    return make_response(redirect(ADDRESS))

@app.route("/logout")
@login_required
def logout():
    session.pop('x-access-token', None)
    return redirect(ADDRESS)

if __name__ == '__main__':
    app.run(host='0.0.0.0')