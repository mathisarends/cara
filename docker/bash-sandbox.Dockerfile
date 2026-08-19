FROM golang:1.25-alpine AS tooling-builder

ARG HUEGO_VERSION=v0.1.0
ARG SPOTI_VERSION=v0.1.0
ARG GO_WITHINGS_VERSION=v0.1.0
ENV CGO_ENABLED=0 GOBIN=/out
RUN go install -trimpath -ldflags="-s -w" "github.com/mathisarends/huego@${HUEGO_VERSION}" && \
    go install -trimpath -ldflags="-s -w" "github.com/mathisarends/spoti@${SPOTI_VERSION}" && \
    go install -trimpath -ldflags="-s -w" "github.com/mathisarends/go-withings/cmd/withings@${GO_WITHINGS_VERSION}"

FROM python:3.14-alpine

RUN apk add --no-cache bash
COPY --from=tooling-builder /out/huego /usr/local/bin/huego
COPY --from=tooling-builder /out/spoti /usr/local/bin/spoti
COPY --from=tooling-builder /out/withings /usr/local/bin/withings

ENTRYPOINT []
CMD ["bash"]
