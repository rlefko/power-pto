#!/bin/bash

# ===============================
# Script: setup-environment.sh
# Description: Sets up the Power PTO development environment.
# Installs prerequisites (Docker, Node.js, yarn, GitHub CLI, pre-commit),
# builds Docker images, runs migrations, and seeds demo data.
# ===============================

set -euo pipefail

# ===============================
# Color Definitions
# ===============================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ===============================
# Emoji Definitions
# ===============================
SUCCESS_EMOJI="✅"
WARNING_EMOJI="⚠️"
ERROR_EMOJI="❌"
DOCKER_EMOJI="🐳"
SETUP_EMOJI="🚀"
BUILD_EMOJI="🛠️"

# ===============================
# Utility Functions
# ===============================

log() {
    local color=$1
    local emoji=$2
    local message=$3
    echo -e "${color}${emoji} ${message}${NC}"
}

spinner() {
    local pid=$1
    local delay=0.1
    local spinstr='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
    local i=0
    while kill -0 "$pid" 2>/dev/null; do
        local temp=${spinstr:i++%${#spinstr}:1}
        printf " ${BLUE}[%s]${NC}" "$temp"
        sleep $delay
        printf "\r"
    done
    printf "    \r"
    wait "$pid"
    return $?
}

error_exit() {
    log "$RED" "$ERROR_EMOJI" "$1"
    exit 1
}

# ===============================
# System Detection
# ===============================

check_system() {
    log "$BLUE" "$SETUP_EMOJI" "Checking system compatibility..."

    OS_TYPE=""
    PACKAGE_MANAGER=""

    case "$OSTYPE" in
        darwin*)
            OS_TYPE="macOS"
            PACKAGE_MANAGER="brew"
            ;;
        linux-gnu*)
            OS_TYPE="Linux"
            if [ -x "$(command -v apt)" ]; then
                PACKAGE_MANAGER="apt"
            elif [ -x "$(command -v dnf)" ]; then
                PACKAGE_MANAGER="dnf"
            elif [ -x "$(command -v brew)" ]; then
                PACKAGE_MANAGER="brew"
            else
                error_exit "Unsupported Linux distribution. Please install Homebrew or use a supported package manager (apt/dnf)."
            fi
            ;;
        msys*|cygwin*|win32*)
            OS_TYPE="Windows"
            PACKAGE_MANAGER="choco"
            ;;
        *)
            error_exit "Unsupported OS: $OSTYPE"
            ;;
    esac

    log "$GREEN" "$SUCCESS_EMOJI" "Detected OS: $OS_TYPE (package manager: $PACKAGE_MANAGER)"
}

# ===============================
# Package Manager Bootstrap
# ===============================

install_homebrew() {
    if [ "$PACKAGE_MANAGER" != "brew" ]; then return; fi

    if command -v brew &> /dev/null; then
        log "$GREEN" "$SUCCESS_EMOJI" "Homebrew is already installed."
        return
    fi

    log "$YELLOW" "$WARNING_EMOJI" "Homebrew not found. Installing..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" &
    if ! spinner $!; then
        error_exit "Failed to install Homebrew."
    fi
    echo

    # Detect brew installation path and add to PATH
    BREW_PREFIX=$(brew --prefix 2>/dev/null || true)
    if [ -z "$BREW_PREFIX" ]; then
        if [ -x "/opt/homebrew/bin/brew" ]; then
            BREW_PREFIX="/opt/homebrew"
        elif [ -x "/home/linuxbrew/.linuxbrew/bin/brew" ]; then
            BREW_PREFIX="/home/linuxbrew/.linuxbrew"
        else
            error_exit "Failed to locate Homebrew after installation."
        fi
    fi
    eval "$("$BREW_PREFIX/bin/brew" shellenv)"

    if command -v brew &> /dev/null; then
        log "$GREEN" "$SUCCESS_EMOJI" "Homebrew installed successfully."
    else
        error_exit "Failed to install Homebrew."
    fi
}

install_chocolatey() {
    if [ "$PACKAGE_MANAGER" != "choco" ]; then return; fi

    if command -v choco &> /dev/null; then
        log "$GREEN" "$SUCCESS_EMOJI" "Chocolatey is already installed."
        return
    fi

    log "$YELLOW" "$WARNING_EMOJI" "Chocolatey not found. Installing..."
    powershell.exe -NoProfile -InputFormat None -ExecutionPolicy Bypass -Command \
        'Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString("https://chocolatey.org/install.ps1"))' &
    if ! spinner $!; then
        error_exit "Failed to install Chocolatey."
    fi
    echo

    if command -v choco &> /dev/null; then
        log "$GREEN" "$SUCCESS_EMOJI" "Chocolatey installed successfully."
    else
        error_exit "Failed to install Chocolatey."
    fi
}

# ===============================
# Package Installation Helper
# ===============================

install_package() {
    local package=$1
    local install_cmd

    export HOMEBREW_NO_AUTO_UPDATE=1

    case "$PACKAGE_MANAGER" in
        brew)   install_cmd="brew install $package" ;;
        apt)    install_cmd="sudo apt-get install -y $package" ;;
        dnf)    install_cmd="sudo dnf install -y $package" ;;
        choco)  install_cmd="choco install $package -y" ;;
        *)      error_exit "Unsupported package manager: $PACKAGE_MANAGER" ;;
    esac

    log "$BLUE" "$BUILD_EMOJI" "Installing $package..."
    $install_cmd &
    if ! spinner $!; then
        error_exit "Failed to install $package."
    fi
    echo

    log "$GREEN" "$SUCCESS_EMOJI" "$package installed."
}

# ===============================
# Docker
# ===============================

install_docker() {
    log "$BLUE" "$DOCKER_EMOJI" "Checking Docker installation..."

    if command -v docker &> /dev/null; then
        log "$GREEN" "$SUCCESS_EMOJI" "Docker is already installed."
    else
        log "$YELLOW" "$WARNING_EMOJI" "Docker not found. Installing..."
        case "$OS_TYPE" in
            macOS)
                install_package "docker"
                log "$BLUE" "$DOCKER_EMOJI" "Launching Docker Desktop..."
                open -a Docker 2>/dev/null || log "$YELLOW" "$WARNING_EMOJI" "Please install and launch Docker Desktop manually: https://docker.com/products/docker-desktop"
                ;;
            Linux)
                if [ "$PACKAGE_MANAGER" == "apt" ]; then
                    sudo apt-get install -y ca-certificates curl gnupg lsb-release
                    sudo mkdir -p /etc/apt/keyrings
                    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
                    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
                    sudo apt-get update
                    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
                elif [ "$PACKAGE_MANAGER" == "dnf" ]; then
                    sudo dnf -y install dnf-plugins-core
                    sudo dnf config-manager --add-repo https://download.docker.com/linux/fedora/docker-ce.repo
                    sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
                    sudo systemctl start docker
                    sudo systemctl enable docker
                elif [ "$PACKAGE_MANAGER" == "brew" ]; then
                    install_package "docker"
                fi
                ;;
            Windows)
                install_package "docker-desktop"
                ;;
        esac
    fi

    # Wait for Docker daemon
    log "$BLUE" "$DOCKER_EMOJI" "Waiting for Docker daemon..."
    local retries=0
    while ! docker info > /dev/null 2>&1; do
        retries=$((retries + 1))
        if [ $retries -gt 60 ]; then
            error_exit "Docker daemon did not start within 2 minutes. Please start Docker Desktop manually and re-run this script."
        fi
        sleep 2
    done
    log "$GREEN" "$SUCCESS_EMOJI" "Docker daemon is running."

    # Verify docker compose is available
    if ! docker compose version > /dev/null 2>&1; then
        error_exit "docker compose is not available. Please install Docker Compose v2: https://docs.docker.com/compose/install/"
    fi
    log "$GREEN" "$SUCCESS_EMOJI" "Docker Compose is available."
}

# ===============================
# Make
# ===============================

install_make() {
    log "$BLUE" "$BUILD_EMOJI" "Checking Make installation..."

    if command -v make &> /dev/null; then
        log "$GREEN" "$SUCCESS_EMOJI" "Make is already installed."
        return
    fi

    log "$YELLOW" "$WARNING_EMOJI" "Make not found. Installing..."
    case "$OS_TYPE" in
        macOS)
            # make comes with Xcode Command Line Tools
            xcode-select --install 2>/dev/null || true
            ;;
        Linux)
            install_package "make"
            ;;
        Windows)
            install_package "make"
            ;;
    esac

    if command -v make &> /dev/null; then
        log "$GREEN" "$SUCCESS_EMOJI" "Make installed successfully."
    else
        error_exit "Failed to install Make."
    fi
}

# ===============================
# Node.js and Yarn
# ===============================

install_node_and_yarn() {
    log "$BLUE" "$BUILD_EMOJI" "Checking Node.js installation..."

    if command -v node &> /dev/null; then
        log "$GREEN" "$SUCCESS_EMOJI" "Node.js is already installed ($(node --version))."
    else
        log "$YELLOW" "$WARNING_EMOJI" "Node.js not found. Installing..."
        case "$PACKAGE_MANAGER" in
            brew)   install_package "node" ;;
            apt)
                curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
                sudo apt-get install -y nodejs
                ;;
            dnf)    install_package "nodejs" ;;
            choco)  install_package "nodejs" ;;
        esac
        log "$GREEN" "$SUCCESS_EMOJI" "Node.js installed ($(node --version))."
    fi

    log "$BLUE" "$BUILD_EMOJI" "Checking yarn installation..."
    if command -v yarn &> /dev/null; then
        log "$GREEN" "$SUCCESS_EMOJI" "yarn is already installed."
    else
        log "$YELLOW" "$WARNING_EMOJI" "yarn not found. Installing..."
        npm install -g yarn &
        if ! spinner $!; then
            error_exit "Failed to install yarn."
        fi
        echo
        log "$GREEN" "$SUCCESS_EMOJI" "yarn installed."
    fi
}

# ===============================
# GitHub CLI
# ===============================

install_github_cli() {
    log "$BLUE" "$BUILD_EMOJI" "Checking GitHub CLI installation..."

    if command -v gh &> /dev/null; then
        log "$GREEN" "$SUCCESS_EMOJI" "GitHub CLI is already installed."
        return
    fi

    log "$YELLOW" "$WARNING_EMOJI" "GitHub CLI not found. Installing..."
    case "$OS_TYPE" in
        macOS)
            install_package "gh"
            ;;
        Linux)
            if [ "$PACKAGE_MANAGER" == "apt" ]; then
                curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg 2>/dev/null
                sudo chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg
                echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
                sudo apt update
                sudo apt install gh -y
            elif [ "$PACKAGE_MANAGER" == "dnf" ]; then
                sudo dnf install 'dnf-command(config-manager)' -y
                sudo dnf config-manager --add-repo https://cli.github.com/packages/rpm/gh-cli.repo
                sudo dnf install gh -y
            elif [ "$PACKAGE_MANAGER" == "brew" ]; then
                install_package "gh"
            fi
            ;;
        Windows)
            install_package "gh"
            ;;
    esac

    if command -v gh &> /dev/null; then
        log "$GREEN" "$SUCCESS_EMOJI" "GitHub CLI installed successfully."
    else
        log "$YELLOW" "$WARNING_EMOJI" "GitHub CLI installation may have failed. You can install it later: https://cli.github.com"
    fi
}

# ===============================
# Pre-commit Hooks
# ===============================

install_pre_commit() {
    log "$BLUE" "$BUILD_EMOJI" "Checking pre-commit installation..."

    if command -v pre-commit &> /dev/null; then
        log "$GREEN" "$SUCCESS_EMOJI" "pre-commit is already installed."
    else
        log "$YELLOW" "$WARNING_EMOJI" "pre-commit not found. Installing..."
        install_package "pre-commit"
    fi

    if [ -f ".pre-commit-config.yaml" ]; then
        pre-commit install
        log "$GREEN" "$SUCCESS_EMOJI" "Pre-commit hooks installed."
    else
        log "$YELLOW" "$WARNING_EMOJI" ".pre-commit-config.yaml not found. Skipping hook installation."
    fi
}

# ===============================
# Environment File
# ===============================

setup_env_file() {
    if [ -f ".env" ]; then
        log "$GREEN" "$SUCCESS_EMOJI" ".env file already exists."
    elif [ -f ".env.example" ]; then
        cp .env.example .env
        log "$GREEN" "$SUCCESS_EMOJI" "Created .env from .env.example."
    else
        log "$YELLOW" "$WARNING_EMOJI" "No .env.example found. Skipping .env creation."
    fi
}

# ===============================
# Frontend Dependencies
# ===============================

install_frontend_deps() {
    log "$BLUE" "$BUILD_EMOJI" "Installing frontend dependencies..."
    (cd frontend && yarn install --frozen-lockfile --ignore-engines) || error_exit "Failed to install frontend dependencies."
    log "$GREEN" "$SUCCESS_EMOJI" "Frontend dependencies installed."
}

# ===============================
# Docker Build and Services
# ===============================

start_services() {
    log "$BLUE" "$DOCKER_EMOJI" "Building and starting Docker services..."
    docker compose up -d --build
    log "$GREEN" "$SUCCESS_EMOJI" "Docker services started."

    # Wait for API to be healthy
    log "$BLUE" "$DOCKER_EMOJI" "Waiting for API to be ready..."
    local retries=0
    local max_retries=60
    while true; do
        if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
            break
        fi
        retries=$((retries + 1))
        if [ $retries -gt $max_retries ]; then
            error_exit "API did not become healthy within 2 minutes. Check logs with: make logs"
        fi
        sleep 2
    done
    log "$GREEN" "$SUCCESS_EMOJI" "API is healthy."
}

run_migrations() {
    log "$BLUE" "$BUILD_EMOJI" "Running database migrations..."
    make migrate
    log "$GREEN" "$SUCCESS_EMOJI" "Migrations complete."
}

run_seed() {
    log "$BLUE" "$BUILD_EMOJI" "Seeding demo data..."
    make seed
    log "$GREEN" "$SUCCESS_EMOJI" "Demo data seeded."
}

# ===============================
# Main
# ===============================

main() {
    log "$BLUE" "$SETUP_EMOJI" "Starting Power PTO development environment setup..."
    echo

    check_system

    # Install package manager
    install_homebrew
    install_chocolatey

    # Install prerequisites
    install_docker
    install_make
    install_node_and_yarn
    install_github_cli
    install_pre_commit

    # Configure environment
    setup_env_file
    install_frontend_deps

    # Build and start everything
    start_services
    run_migrations
    run_seed

    echo
    log "$GREEN" "🎉" "Setup complete! Power PTO is running:"
    echo
    echo -e "  ${BLUE}Frontend:${NC}     http://localhost:5173"
    echo -e "  ${BLUE}API:${NC}          http://localhost:8000"
    echo -e "  ${BLUE}Swagger Docs:${NC} http://localhost:8000/docs"
    echo
    echo -e "  Run ${GREEN}make logs${NC} to view service logs."
    echo -e "  Run ${GREEN}make down${NC} to stop all services."
    echo
}

main
