FROM oraclelinux:9
RUN dnf install -y iptables conntrack-tools git && \
    dnf clean all
#RUN alternatives --set iptables /usr/sbin/iptables-legacy && \
#    alternatives --set ip6tables /usr/sbin/ip6tables-legacy
RUN dnf install -y python3 python3-pip git
RUN pip3 install Flask flask-login oauthlib PyJWT requests

#ARG GIT_USERNAME
#ARG GIT_PASSWORD
#RUN echo "machine github.com login ${GIT_USERNAME} password ${GIT_PASSWORD}" > ~/.netrc

COPY network_scripts/setup_network.sh /usr/local/bin/setup_network.sh
RUN chmod +x /usr/local/bin/setup_network.sh
CMD ["/usr/local/bin/setup_network.sh"]
WORKDIR /ONA
RUN git clone https://github.com/cj667113/ONA.git .
EXPOSE 1-65535
ENV FLASK_APP=/ONA/flask/app.py
CMD ["flask","run","--host=0.0.0.0","--port=5000"]