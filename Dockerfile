FROM alpine:3.23
ARG KUBECTL_VERSION=v1.30.4
ARG TARGETARCH=amd64
RUN apk add --no-cache bash jq openssl curl coreutils util-linux ca-certificates gawk \
    && curl -fsSLo /usr/local/bin/kubectl "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${TARGETARCH}/kubectl" \
    && curl -fsSLo /tmp/kubectl.sha256 "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${TARGETARCH}/kubectl.sha256" \
    && printf '%s  /usr/local/bin/kubectl\n' "$(cat /tmp/kubectl.sha256)" | sha256sum -c - \
    && chmod 755 /usr/local/bin/kubectl \
    && rm /tmp/kubectl.sha256 \
    && adduser -D -u 10001 sentinel
COPY --chmod=755 DevOps_K8s_Sentinel_FINAL_GP.sh /usr/local/bin/devopssentinel
USER 10001:10001
ENV HOME=/home/sentinel
WORKDIR /home/sentinel
ENTRYPOINT ["/usr/local/bin/devopssentinel"]
CMD ["--help"]
