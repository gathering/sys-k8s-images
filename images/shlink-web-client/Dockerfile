# shlink-web-client that also listens on IPv6, for IPv6-only pods. Upstream
# declined the change: https://github.com/shlinkio/shlink-web-client/pull/2053
FROM shlinkio/shlink-web-client:4.9.1@sha256:732c291bcc099d6ff51038bcfba374be87494fa2916683a44d3135ea57cbe935

# The grep fails the build when upstream's listen line has changed.
USER 0
RUN sed -i -E 's/^([[:space:]]*)listen 8080 default_server;$/&\n\1listen [::]:8080 default_server;/' /etc/nginx/conf.d/default.conf \
    && grep -q 'listen \[::\]:8080 default_server;' /etc/nginx/conf.d/default.conf
# Upstream's user.
USER 101
