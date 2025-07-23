# NS-3 Simulator for RDMA Network at Cross Data Center

This is a Github repository based on [https://github.com/alibaba-edu/High-Precision-Congestion-Control](https://github.com/alibaba-edu/High-Precision-Congestion-Control) and [https://github.com/conweave-project/conweave-ns3](https://github.com/conweave-project/conweave-ns3).

We recommend you to run it in Docker. [Here](#Run-in-Docker) is how to build the Docker image.

## Run in Docker

### Build the Docker image

1. Create a Dockerfile or use the one provided in the repository.

```Dockerfile
FROM ubuntu:20.04
ARG DEBIAN_FRONTEND=noninteractive

RUN apt update && apt install -y gnuplot python python3 python3-pip build-essential libgtk-3-0 bzip2 wget git screen && rm -rf /var/lib/apt/lists/* && pip3 install numpy matplotlib cycler
WORKDIR /root
```

2. Build the Docker image.

```bash
docker build -t ns3-docker .
```

3. Run the Docker container.

```bash
docker run -it -v $(pwd):/root ns-docker
```

### Run the NS-3 Simulator

1. Configure and build N3-3

```bash
cd ns-3.19
./waf configure --build-profile=optimized
./waf build
```

2. Run the Simulator for RDMA Network at Cross Data Center

```bash
cd ns-3.19
./run_cross_dc_batch.sh
```

### Analyze the Results

> Waiting for update.

