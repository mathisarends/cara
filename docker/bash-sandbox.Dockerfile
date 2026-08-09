FROM golang:1.25-alpine AS spogo-builder

ARG SPOGO_VERSION=v0.10.3
ENV CGO_ENABLED=0 GOBIN=/out
RUN go install -trimpath -ldflags="-s -w" "github.com/steipete/spogo/cmd/spogo@${SPOGO_VERSION}"

FROM python:3.14-alpine

RUN apk add --no-cache bash
COPY --from=spogo-builder /out/spogo /usr/local/bin/spogo

ENTRYPOINT []
CMD ["bash"]
