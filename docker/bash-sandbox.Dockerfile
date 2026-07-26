FROM golang:1.24-alpine AS cara-tool-builder

WORKDIR /src/cara-tool
COPY tools/cara-tool/ ./
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/cara-tool .

FROM python:3.14-alpine

ARG SPOTIFYIFY_VERSION=0.7.0

RUN apk add --no-cache bash
RUN pip install --no-cache-dir "spotifyify[cli]==${SPOTIFYIFY_VERSION}"
COPY --from=cara-tool-builder /out/cara-tool /usr/local/bin/cara-tool

ENTRYPOINT []
CMD ["bash"]
