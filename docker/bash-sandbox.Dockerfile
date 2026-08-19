FROM golang:1.26-alpine AS tooling-builder

ENV CGO_ENABLED=0 GOBIN=/out
COPY install-tools.sh tools.txt /tmp/
RUN chmod +x /tmp/install-tools.sh && /tmp/install-tools.sh /tmp/tools.txt

FROM python:3.14-alpine

RUN apk add --no-cache bash
RUN pip install --no-cache-dir PyYAML==6.0.3
COPY --from=tooling-builder /out/ /usr/local/bin/

ENTRYPOINT []
CMD ["bash"]
