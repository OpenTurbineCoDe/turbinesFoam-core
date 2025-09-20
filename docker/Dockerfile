# Use the official OpenFOAM v2406 image (ESI-OpenCFD).
# If your environment uses a different tag, adjust it here.
FROM openfoam/openfoam:v2406

# Install OS deps for building and Python server
USER root
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    build-essential ccache cmake git python3 python3-pip python3-venv \
 && rm -rf /var/lib/apt/lists/*

# Create a non-root workspace user (many OpenFOAM images already have an 'openfoam' user;
# if so, you can drop this and just use that user.)
ARG USERNAME=openfoam
ARG USER_UID=1000
ARG USER_GID=1000
RUN if ! id -u $USERNAME >/dev/null 2>&1; then \
      groupadd --gid $USER_GID $USERNAME && \
      useradd --uid $USER_UID --gid $USER_GID -m -s /bin/bash $USERNAME; \
    fi

# Workdir layout inside container
ENV CORE_HOME=/opt/turbinesFoam-core
ENV SRC_DIR=$CORE_HOME/src
ENV PS_DIR=$CORE_HOME/protocol-server
WORKDIR $CORE_HOME

# Copy repo content
# (Make sure your .dockerignore excludes build artifacts)
COPY --chown=$USERNAME:$USERNAME src/ $SRC_DIR/
COPY --chown=$USERNAME:$USERNAME protocol-server/ $PS_DIR/
COPY --chown=$USERNAME:$USERNAME scripts/ scripts/

# Set up Python venv for protocol server
USER $USERNAME
RUN python3 -m venv $CORE_HOME/.venv && \
    . $CORE_HOME/.venv/bin/activate && \
    pip install --upgrade pip && \
    pip install -r $PS_DIR/requirements.txt

# Compile custom solvers with OpenFOAM environment
# We need 'bash -lc' so that 'source /opt/openfoam*/etc/bashrc' applies to the shell
SHELL ["/bin/bash", "-lc"]

# Point WM_PROJECT_USER_DIR to a per-user space so wmake can deposit build products
ENV WM_PROJECT_USER_DIR=/home/$USERNAME/OpenFOAM/$USERNAME-v2406

RUN mkdir -p "$WM_PROJECT_USER_DIR" && \
    source /opt/openfoam*/etc/bashrc && \
    export PATH=$WM_PROJECT_DIR/wmake:$PATH && \
    cd "$SRC_DIR/PimpleFoamMy" && wmake && \
    cd "$SRC_DIR/turbinesFoamMy" && wmake

# Add solvers to PATH (OpenFOAM typically finds them via $FOAM_USER_APPBIN)
RUN echo 'source /opt/openfoam*/etc/bashrc' >> ~/$USERNAME.bashrc

# Expose protocol server port
EXPOSE 5555

# Startup: launch protocol server
# Ensures OpenFOAM env is available for any runtime needs
ENV VENV=$CORE_HOME/.venv
CMD source /opt/openfoam*/etc/bashrc && \
    source $VENV/bin/activate && \
    bash $PS_DIR/start.sh
