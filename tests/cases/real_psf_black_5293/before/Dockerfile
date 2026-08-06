COPY . /src/
ENV VIRTUAL_ENV=/opt/venv
ENV HATCH_BUILD_HOOKS_ENABLE=1
ENV PIP_UPLOADED_PRIOR_TO=P2D
# Install build tools to compile black + dependencies
RUN apt update && apt install -y build-essential git python3-dev

ENV PATH="$VIRTUAL_ENV/bin:$PATH"
RUN python -m venv $VIRTUAL_ENV
RUN cd /src \
    && pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --group hatch \
    && hatch build -t wheel \
