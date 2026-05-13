# ONA Setup and Deployment Guide

## Step 1: Create a Compute Instance and Gather Public IP Address

1. Log in to your OCI account and navigate to the Compute Instances page.
2. Create a new Compute Instance and note down its public IP address.

## Step 2: Create a Confidential Application

**Important:** Due to a bug in the OCI Console, you may need to leave the "Allow non-HTTPS URLs" box unchecked during creation. You can re-add it after creating the Confidential Application.

Use the public IP address of the Compute Node in the redirect URL.

Create a Confidential Application and retrieve the CLIENT ID, SECRET AND URL and enable the Confidential Application.

![alt text](images/CA-PAGE-1.png "Page 1")

![alt text](images/CA-PAGE-2.png "Page 2")

![alt text](images/CA-PAGE-3.png "Page 3")

![alt text](images/CA-PAGE-4.png "Page 4")

Make sure to enable the Confidential Application in the OCI Console.

Get the Domain URL
![alt text](images/IDCS-URL.png "Domain URL")

## Step 3: Clone the Git Repo
    git clone https://github.com/cj667113/ONA.git

## Step 4: Install Docker
https://docs.docker.com/engine/install/

## Step 5: Docker Build
Run this from the repository root:

    docker build --no-cache -t ona .

If your shell is already inside the `docker/` directory, use the repository-root Dockerfile and keep the repository root as the build context:

    docker build --no-cache -f ../Dockerfile -t ona ..

## Step 6: Run Docker Container
To run ONA as a docker container run:

    ADDRESS=https://DNS_NAME_FOR_THE_NODE
    ORACLE_CLIENT_ID=ID FROM OCI CONFIDENTIAL APP
    ORACLE_IDCS_SECRET=SECRET FROM OCI CONFIDENTIAL APP
    ORACLE_IDCS_URL=Domain URL
    ONA_SECRET_KEY=$(openssl rand -hex 32)

    docker run --network host --privileged -d --restart always \
      -v /lib/modules:/lib/modules:ro \
      -v ona-config:/ONA/flask/instance \
      -e ORACLE_CLIENT_ID="$ORACLE_CLIENT_ID" \
      -e ORACLE_IDCS_SECRET="$ORACLE_IDCS_SECRET" \
      -e ORACLE_IDCS_URL="$ORACLE_IDCS_URL" \
      -e ADDRESS="$ADDRESS" \
      -e ONA_SECRET_KEY="$ONA_SECRET_KEY" \
      ona

Use an HTTPS `ADDRESS` when TLS is terminated in front of the container. The OCI Confidential Application redirect URL must match the same scheme and host, for example `https://DNS_NAME_FOR_THE_NODE/login/callback`.

If `/login/callback` logs `InsecureTransportError: OAuth 2 MUST utilize https`, Flask is receiving the callback as HTTP. Fix the public URL and redirect URL to use HTTPS, or make sure your reverse proxy/load balancer forwards `X-Forwarded-Proto: https`.

For lab-only direct Flask HTTP deployments, set `ADDRESS=http://IP_OR_DNS_OF_THE_NODE:5000`, add `-e OAUTHLIB_INSECURE_TRANSPORT=1` to `docker run`, and configure the OCI redirect URL as `http://IP_OR_DNS_OF_THE_NODE:5000/login/callback`.

The `iptables` and `nftables` packages install user-space tools, not kernel modules. The container uses host networking and host netfilter state, so kernel modules must be available on the Docker host. Keep the `/lib/modules` mount in the `docker run` command above if you want the container entrypoint to load netfilter modules, or load them on the host before starting ONA.

## Step 7: Optional Object Storage Backups
The Backups panel in the UI can list Object Storage buckets, create zip backups of the ONA-managed iptables rules, schedule recurring backups, and restore a selected backup.

ONA uses OCI instance principal authentication for backups. Put the compute instance in a dynamic group and grant it access to the backup compartment, for example:

    Allow dynamic-group ONA_DYNAMIC_GROUP to inspect buckets in compartment ONA_COMPARTMENT
    Allow dynamic-group ONA_DYNAMIC_GROUP to manage objects in compartment ONA_COMPARTMENT

In the UI, enter the region, compartment OCID, optional namespace, refresh buckets, select a bucket, set retention, and save the backup policy. The backup list shows `.zip` objects in the selected bucket so a fresh ONA deployment can restore from existing backups. Scheduled backups can be enabled or disabled from the panel and run inside the Flask process once per minute, so deploy one ONA app process for a single backup schedule owner.

The gateway dashboard streams updates in place about every 5 seconds with CPU, memory, conntrack, NAT port, connection, packet, and network throughput statistics. Dashboard history is stored in `/ONA/flask/instance/dashboard_history.json` by default so recent metrics are available after browser refreshes, new logins, and container restarts when the instance directory is mounted as a persistent volume. Set `ONA_DASHBOARD_HISTORY_FILE` to override the storage path. Each trend chart can be downloaded as a PNG, and the dashboard can package all chart PNGs into a single zip from the Metric Trends toolbar.

## Step 8: Optional Secondary VNIC SNAT Pool
ONA can scan the instance metadata service for attached VNICs and their primary or secondary private IPs. After attaching secondary VNICs or adding secondary private IPs in OCI, use `Scan` to inspect available addresses or `Scan & Configure` in the Source NAT tab to configure missing live OS addresses with `oci-network-config configure` when available or `ip addr add` as a fallback. Select the addresses to use, enable the SNAT pool, and click `Apply SNAT Pool`. SNAT pools are applied in separate managed chains with connection marks and policy routes so connections using a source IP assigned to a secondary VNIC leave through that VNIC's OS interface.

For NAT forwarding, disable source/destination check on every VNIC used by the appliance. Oracle recommends `oci-network-config` for Oracle Linux secondary VNIC OS configuration; ONA falls back to live `ip` commands when that utility is not present.

## Step 9: Access the UI
In a web browser go to `$ADDRESS`.

After you Log into the appliance you should be redirected back to a page like this:

![alt text](images/ONA-Landing.png "Page Landing")
