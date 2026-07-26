FROM golang:1.24-alpine AS cara-tool-builder

WORKDIR /src/cara-tool
COPY tools/cara-tool/ ./
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/cara-tool .

FROM python:3.13-alpine

RUN apk add --no-cache bash
COPY --from=cara-tool-builder /out/cara-tool /usr/local/bin/cara-tool

ENTRYPOINT []
CMD ["bash"]
