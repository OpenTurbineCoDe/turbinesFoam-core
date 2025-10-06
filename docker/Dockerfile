# ---------------------------------------------------------------------------
# Base: ESI-OpenCFD OpenFOAM v2406
# ---------------------------------------------------------------------------
FROM opencfd/openfoam-default:2406

# ---------------------------------------------------------------------------
# System packages (runtime + light tools for dev/aliases)
# ---------------------------------------------------------------------------
USER root
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      build-essential ccache cmake git \
      python3 python3-pip python3-venv \
      curl jq \
  && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# User/group setup
# ---------------------------------------------------------------------------
ARG USERNAME=openfoam
ARG USER_UID=1000
ARG USER_GID=1000

RUN set -eux; \
  if getent group "${USER_GID}" >/dev/null; then \
    TARGET_GRP="$(getent group "${USER_GID}" | cut -d: -f1)"; \
  else \
    groupadd -g "${USER_GID}" "${USERNAME}"; \
    TARGET_GRP="${USERNAME}"; \
  fi; \
  if id -u "${USERNAME}" >/dev/null 2>&1; then \
    usermod -g "${TARGET_GRP}" "${USERNAME}" || true; \
  else \
    if getent passwd "${USER_UID}" >/dev/null; then \
      useradd -m -g "${TARGET_GRP}" -s /bin/bash "${USERNAME}"; \
    else \
      useradd -m -u "${USER_UID}" -g "${TARGET_GRP}" -s /bin/bash "${USERNAME}"; \
    fi; \
  fi; \
  test -d "/home/${USERNAME}" || mkdir -p "/home/${USERNAME}"; \
  chown -R "${USERNAME}:$(id -g ${USERNAME})" "/home/${USERNAME}"

# ---------------------------------------------------------------------------
# Layout & fixed env (ensure OpenFOAM uses the right user dir)
# ---------------------------------------------------------------------------
ENV CORE_HOME=/opt/turbinesFoam-core \
    SRC_DIR=/opt/turbinesFoam-core/src \
    PS_DIR=/opt/turbinesFoam-core/protocol-server \
    FOAM_BASHRC=/usr/lib/openfoam/openfoam2406/etc/bashrc

# Force OpenFOAM to use /home/openfoam/OpenFOAM/openfoam-v2406 and not user-v2406
ENV USER=${USERNAME} \
    LOGNAME=${USERNAME} \
    WM_PROJECT_USER_DIR=/home/${USERNAME}/OpenFOAM/${USERNAME}-v2406 \
    FOAM_RUN=/home/${USERNAME}/OpenFOAM/${USERNAME}-v2406/run

WORKDIR ${CORE_HOME}

# Ensure dirs exist and are owned by the user
RUN mkdir -p "${SRC_DIR}" "${PS_DIR}" "${CORE_HOME}/scripts" "${FOAM_RUN}" \
  && chown -R ${USERNAME}:$(id -g ${USERNAME}) "/home/${USERNAME}" "${CORE_HOME}"

# ---------------------------------------------------------------------------
# Python deps – copy only requirements first to leverage Docker cache
# ---------------------------------------------------------------------------
COPY protocol-server/requirements.txt ${PS_DIR}/requirements.txt
RUN chown -R ${USERNAME}:$(id -g ${USERNAME}) "${PS_DIR}"

USER ${USERNAME}
RUN python3 -m venv ${CORE_HOME}/.venv \
  && . ${CORE_HOME}/.venv/bin/activate \
  && pip install --upgrade pip \
  && pip install -r ${PS_DIR}/requirements.txt

# ---------------------------------------------------------------------------
# Copy sources, scripts, protocol server (as root), fix ownership & perms
# ---------------------------------------------------------------------------
USER root
COPY src/ ${SRC_DIR}/
COPY protocol-server/ ${PS_DIR}/
COPY scripts/ ${CORE_HOME}/scripts/
RUN chown -R ${USERNAME}:$(id -g ${USERNAME}) "${CORE_HOME}" \
  && chmod +x ${PS_DIR}/start.sh || true \
  && chmod +x ${CORE_HOME}/scripts/compile_solvers.sh || true

# ---------------------------------------------------------------------------
# Developer convenience files (.bash_aliases) baked into the image
#   Expect: protocol-server/resources/.bash_aliases present in build context
# ---------------------------------------------------------------------------
COPY protocol-server/resources/.bash_aliases /home/${USERNAME}/.bash_aliases
RUN chown ${USERNAME}:$(id -g ${USERNAME}) /home/${USERNAME}/.bash_aliases

# ---------------------------------------------------------------------------
# Use Bash for RUN steps that need sourcing
# ---------------------------------------------------------------------------
SHELL ["/bin/bash", "-lc"]

# Verify FOAM_BASHRC exists
RUN test -f "${FOAM_BASHRC}" || (echo "ERROR: FOAM_BASHRC not found at ${FOAM_BASHRC}" && exit 1)

# ---------------------------------------------------------------------------
# Compile custom code (non-root), with strict shell and correct env
# ---------------------------------------------------------------------------
USER ${USERNAME}
RUN set -euo pipefail \
  && set +u \
  && source "${FOAM_BASHRC}" \
  && set -u \
  && mkdir -p "${WM_PROJECT_USER_DIR}" \
  && SRC_DIR="${SRC_DIR}" FOAM_BASHRC="${FOAM_BASHRC}" "${CORE_HOME}/scripts/compile_solvers.sh"

# ---------------------------------------------------------------------------
# Interactive shell quality-of-life: export overrides, source FOAM & aliases
# ---------------------------------------------------------------------------
RUN printf '\n# --- User dir overrides (persist across shells) ---\n' >> /home/${USERNAME}/.bashrc \
  && printf 'export WM_PROJECT_USER_DIR=/home/%s/OpenFOAM/%s-v2406\n' "${USERNAME}" "${USERNAME}" >> /home/${USERNAME}/.bashrc \
  && printf 'export FOAM_RUN=$WM_PROJECT_USER_DIR/run\n' >> /home/${USERNAME}/.bashrc \
  && printf '\n# --- OpenFOAM env ---\nsource %s\n' "${FOAM_BASHRC}" >> /home/${USERNAME}/.bashrc \
  && printf '\n# --- User aliases ---\nif [ -f ~/.bash_aliases ]; then . ~/.bash_aliases; fi\n' >> /home/${USERNAME}/.bashrc

# Seed the run directory with any case resources you want available
RUN mkdir -p "${FOAM_RUN}" \
  && if [ -d "${SRC_DIR}/turbinesFoamMy/tutorials/resources" ]; then \
       cp -r ${SRC_DIR}/turbinesFoamMy/tutorials/resources/* "${FOAM_RUN}/" || true; \
     fi

# ---------------------------------------------------------------------------
# Expose protocol server port
# ---------------------------------------------------------------------------
EXPOSE 5555

# ---------------------------------------------------------------------------
# Runtime: activate venv, then start protocol server (start.sh handles FOAM env if needed)
# ---------------------------------------------------------------------------
ENV VENV=${CORE_HOME}/.venv
ENTRYPOINT [ "bash", "-lc", "source \"$VENV/bin/activate\" && exec \"$PS_DIR/start.sh\"" ]
