FROM oraclelinux:9
RUN dnf install -y iptables conntrack-tools iproute kmod oci-utils python3 python3-pip && \
    dnf clean all

WORKDIR /ONA
COPY flask/requirements.txt /ONA/flask/requirements.txt
RUN pip3 install --no-cache-dir -r /ONA/flask/requirements.txt
COPY flask /ONA/flask
COPY docker/network_scripts/setup_network.sh /usr/local/bin/setup_network.sh
RUN chmod +x /usr/local/bin/setup_network.sh

ENV FLASK_APP=/ONA/flask/app.py
EXPOSE 5000
ENTRYPOINT ["/usr/local/bin/setup_network.sh"]
CMD ["flask","run","--host=0.0.0.0","--port=5000"]
