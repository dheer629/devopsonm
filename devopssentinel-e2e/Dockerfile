FROM devopsonm-sentinel:4.2.1
USER root
# git-daemon provides /usr/libexec/git-core/git-http-backend, required by the
# local smart-HTTP fixture repository. Alpine 3.23's base git package omits it.
RUN apk add --no-cache python3 git git-daemon postgresql-client
USER 10001:10001
ENTRYPOINT []
CMD ["sleep", "3600"]
