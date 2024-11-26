# SETUP
Log into OCI and create a Compute Instance and gather the public IP address.

Create a Confidential Application and retrieve the CLIENT ID, SECRET AND URL and enable the Confidential Application.

![alt text](images/CA-PAGE-1.png "Page 1")

Use the Public IP Address of the Compute Node in the redirect URL.

There is a bug in the OCI Console that will prevent you from creating the Confidential Application with "Allow non-HTTPS URLs". You may need to leave that box unchecked and readd it after creation of the Confidential Application.

![alt text](images/CA-PAGE-2.png "Page 2")

![alt text](images/CA-PAGE-3.png "Page 3")

![alt text](images/CA-PAGE-4.png "Page 4")

Make sure to enable the Confidential Application in the OCI Console.

Get the Domain URL
![alt text](images/IDCS-URL.png "Domain URL")

# Clone the Git Repo
    git clone https://github.com/cj667113/ONA.git

# Install Docker
https://docs.docker.com/engine/install/

# DOCKER BUILD
    docker build --no-cache -t ona .

# DOCKER
To run ONA as a docker container run:

    ADDRESS=IP of the NODE
    ORACLE_CLIENT_ID= ID FROM OCI CONFIDENTIAL APP
    ORACLE_IDCS_SECRET=SECRET FROM OCI CONFIDENTIAL APP
    ORACLE_IDCS_URL=Domain URL

    docker run --network host --privileged -d --restart always -e ORACLE_CLIENT_ID="$ORACLE_CLIENT_ID" -e ORACLE_IDCS_SECRET="$ORACLE_IDCS_SECRET" -e ORACLE_IDCS_URL="$ORACLE_IDCS_URL" -e ADDRESS="http://$ADDRESS:5000" ona

# Log in
In a web browser go to http://$ADDRESS:5000