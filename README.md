# LKT-LNS

## Build docker image

1. Add ssh key in ssh agent

```bash
ssh-add ~/.ssh/id_rsa
```

2. Build image

```bash
docker buildx build . \
  --ssh default="$SSH_AUTH_SOCK" \
  --tag lkt-lns:latest
```

3. Run image

```bash
docker run -d --name lkt-lns lkt-lns:latest
```
