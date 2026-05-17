FROM node:20-alpine

# Install Claude Code CLI (provides the `claude` binary) + proxy server
RUN npm install -g @anthropic-ai/claude-code claude-max-api-proxy

# Port the proxy listens on
EXPOSE 3456

# CLAUDE_CODE_OAUTH_TOKEN must be passed at runtime via docker-compose / Portainer
# e.g.  CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-...
CMD ["claude-max-api", "3456"]
