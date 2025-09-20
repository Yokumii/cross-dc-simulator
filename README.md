# NS-3 Simulator for RDMA Network at Cross Data Center

This is a Github repository based on [https://github.com/alibaba-edu/High-Precision-Congestion-Control](https://github.com/alibaba-edu/High-Precision-Congestion-Control) and [https://github.com/conweave-project/conweave-ns3](https://github.com/conweave-project/conweave-ns3).

We recommend you to run it in Docker. [Here](#Run-in-Docker) is how to build and run the Docker image.

## Run in Docker

```shell
# Build the Docker image
docker build -t ns-docker .
# Run the Docker container
docker run -it -v $(pwd):/root ns-docker
```

## Run the NS-3 Simulator

1. Configure and build N3-3

```shell
bash -c "cd simulation; ./waf configure --build-profile=optimized; ./waf build"
```

2. Run the Simulator for RDMA Network at Cross Data Center

```shell
bash scripts/run_cross_dc_quick.sh
```
