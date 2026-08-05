FROM ubuntu:22.04

# ruleid: dockerfile-hardcoded-secret-env
ENV DB_PASSWORD=SuperSecret123

# ruleid: dockerfile-hardcoded-secret-env
ARG API_KEY=sk-abcdef1234567890

# ok: dockerfile-hardcoded-secret-env
ARG API_KEY=$BUILD_API_KEY

# ok: dockerfile-hardcoded-secret-env
ENV APP_PORT=8080
