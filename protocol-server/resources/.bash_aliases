# ~/.bash_aliases
# ---------------------------------------------------------
# Convenience for turbinesFoam protocol server containers
# ---------------------------------------------------------

alias py='python3'

# --- Core protocol interactions ---
alias pingcore='curl -s http://localhost:5555/initialize | jq .'
alias stepcore='curl -s -X POST http://localhost:5555/step -H "Content-Type: application/json" \
  -d "{\"t\":0.0,\"dt\":0.1,\"inputs\":{\"omega\":0.8}}" | jq .'

# --- Docker management helpers ---
alias dps="docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"
alias dstop='docker stop $(docker ps -q)'
alias dclean='docker system prune -f'
alias dlog='docker logs -f $(docker ps -q --filter ancestor=turbines-core-proto:step1)'
alias tailcore='docker logs $(docker ps -q --filter ancestor=turbines-core-proto:step1) | tail -n 20'

# --- Run container interactively ---
alias runcore='docker run --rm -it -p 5555:5555 turbines-core-proto:step1 bash'

# --- Debugging and inspection ---
alias pyreqs='pip list | grep -E "fastapi|uvicorn"'
alias whereami='echo "User: $(whoami) | Dir: $(pwd) | Python: $(python3 --version)"'
