COPY . /src/
ENV VIRTUAL_ENV=/opt/venv
ENV HATCH_BUILD_HOOKS_ENABLE=1
# Install build tools to compile black + dependencies
RUN apt update && apt install -y build-essential git python3-dev

ENV PATH="$VIRTUAL_ENV/bin:$PATH"
RUN python -m venv $VIRTUAL_ENV
RUN cd /src \
    # virtualenv 20.39 uses pip 26.0 - use `ENV ...=P2D` once we bump virtualenv/hatch
    && export PIP_UPLOADED_PRIOR_TO=$(date -u -d "2 days ago" +%Y-%m-%dT%H:%M:%SZ) \
    && pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --group hatch \
    && hatch build -t wheel \
