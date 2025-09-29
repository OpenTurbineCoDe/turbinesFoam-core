# Base: ESI-OpenCFD OpenFOAM v2406
FROM opencfd/openfoam-default:2406

# System packages
USER root
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    build-essential ccache cmake git python3 python3-pip python3-venv \
 && rm -rf /var/lib/apt/lists/*

# --- Idempotent user/group setup ---------------------------------------------
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
# -----------------------------------------------------------------------------

# Layout
ENV CORE_HOME=/opt/turbinesFoam-core \
    SRC_DIR=/opt/turbinesFoam-core/src \
    PS_DIR=/opt/turbinesFoam-core/protocol-server
WORKDIR $CORE_HOME

# Ensure dirs exist; hand to $USERNAME
RUN mkdir -p "$SRC_DIR" "$PS_DIR" "$CORE_HOME/scripts" && chown -R $USERNAME:$(id -g $USERNAME) "$CORE_HOME"

# Copy only Python reqs first for cache
COPY protocol-server/requirements.txt $PS_DIR/requirements.txt
RUN chown -R $USERNAME:$(id -g $USERNAME) "$PS_DIR"

# Create venv & install deps as non-root
USER $USERNAME
RUN python3 -m venv $CORE_HOME/.venv && \
    . $CORE_HOME/.venv/bin/activate && \
    pip install --upgrade pip && \
    pip install -r $PS_DIR/requirements.txt

# Copy the rest (as root), then fix ownership
USER root
COPY src/ $SRC_DIR/
COPY protocol-server/ $PS_DIR/
COPY scripts/ $CORE_HOME/scripts/
RUN chown -R $USERNAME:$(id -g $USERNAME) "$CORE_HOME" && \
    chmod +x $PS_DIR/start.sh || true && \
    chmod +x $CORE_HOME/scripts/compile_solvers.sh || true

# OpenFOAM env path for this image
ENV FOAM_BASHRC=/usr/lib/openfoam/openfoam2406/etc/bashrc

# Use Bash for sourcing
SHELL ["/bin/bash", "-lc"]

# Verify FOAM_BASHRC present
RUN test -f "$FOAM_BASHRC" || (echo "ERROR: FOAM_BASHRC not found at $FOAM_BASHRC" && exit 1)

# Per-user build dir
ENV WM_PROJECT_USER_DIR=/home/$USERNAME/OpenFOAM/$USERNAME-v2406

# Build custom code via your script
USER $USERNAME
RUN set +eux; \
    source "$FOAM_BASHRC"; \
    set -e; \
    mkdir -p "$WM_PROJECT_USER_DIR"; \
    SRC_DIR="$SRC_DIR" FOAM_BASHRC="$FOAM_BASHRC" "$CORE_HOME/scripts/compile_solvers.sh"

# Make env available in interactive shells
RUN echo 'source "$FOAM_BASHRC"' >> ~/.bashrc

# Expose protocol server port
EXPOSE 5555

# Runtime: source OpenFOAM + venv, then start server
# Runtime: activate venv, then start server (bashrc handled inside start.sh)
ENV VENV=$CORE_HOME/.venv
ENTRYPOINT [ "bash", "-lc", "source \"$VENV/bin/activate\" && exec \"$PS_DIR/start.sh\"" ]

