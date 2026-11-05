#!/usr/bin/env bash
# ==============================================================================
# COUCHE 1 & 2 : INSTALLATION AUTOMATIQUE DE LA SONDE RÉSEAU (SURICATA + MININET)
# ==============================================================================
# Ce script s'exécute sur votre VM Ubuntu 24.04 LTS.
# Il installe de manière pédagogique :
#   1. Docker & Docker Compose (pour le Serveur Central et Kind)
#   2. Mininet & Open vSwitch (pour simuler le réseau d'entreprise et le port SPAN)
#   3. Suricata IDS (pour détecter les attaques réseau sur l'interface span0)
#   4. Kind & kubectl (pour le cluster Kubernetes)
# ==============================================================================

set -e

echo "======================================================================"
echo " [ÉTAPE 1/4] Installation de Mininet, Open vSwitch et outils de test"
echo "======================================================================"
sudo apt-get update
sudo apt-get install -y \
  mininet \
  openvswitch-switch \
  nmap \
  curl \
  jq \
  tcpdump \
  python3-pip

echo "======================================================================"
echo " [ÉTAPE 2/4] Installation de Suricata IDS (Détection d'intrusion SOC)"
echo "======================================================================"
sudo apt-get install -y suricata
# Mise à jour de la base de signatures d'attaques Emerging Threats (ET Open)
sudo suricata-update || true
# Donner les droits de lecture sur eve.json au conteneur Grafana Alloy
sudo chmod -R 755 /var/log/suricata

echo "======================================================================"
echo " [ÉTAPE 3/4] Installation de Kind et kubectl (Kubernetes léger)"
echo "======================================================================"
if ! command -v kind &> /dev/null; then
  curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.24.0/kind-linux-amd64
  chmod +x ./kind
  sudo mv ./kind /usr/local/bin/kind
fi

if ! command -v kubectl &> /dev/null; then
  curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
  chmod +x ./kubectl
  sudo mv ./kubectl /usr/local/bin/kubectl
fi

echo "======================================================================"
echo " [ÉTAPE 4/4] Tout est installé !"
echo " Pour lancer Suricata en écoute temps réel sur le port miroir Mininet :"
echo "   sudo suricata -i span0 -D"
echo "======================================================================"
