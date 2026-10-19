#!/bin/zsh -f
# Read only the inherited process environment. Never print variable values.
# Presence does not establish active authentication, proxy use or precedence.
claude_check_keys=(
  ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN CLAUDE_CODE_OAUTH_TOKEN
  ANTHROPIC_BASE_URL CLAUDE_CONFIG_DIR ANTHROPIC_PROFILE
  CLAUDE_CODE_USE_BEDROCK CLAUDE_CODE_USE_VERTEX CLAUDE_CODE_USE_FOUNDRY
  HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY
  http_proxy https_proxy all_proxy no_proxy
)
for claude_check_key in "${claude_check_keys[@]}"; do
  if (( ${+parameters[$claude_check_key]} )); then
    if [[ -z "${(P)claude_check_key}" ]]; then
      claude_check_state=empty
    else
      claude_check_state=present
    fi
  else
    claude_check_state=absent
  fi
  printf 'process\t%s\t%s\n' "$claude_check_key" "$claude_check_state"
done
