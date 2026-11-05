#!/usr/bin/env bash
# ==============================================================================
# SCÉNARIOS DE TEST NOC/SOC (Génération de trafic normal et d'attaques)
# ==============================================================================
# Ce script permet de vérifier que toute la chaîne fonctionne de bout en bout :
#   Trafic -> Port Miroir OVS (span0) -> Suricata (eve.json) -> Alloy -> Loki -> Grafana
# ==============================================================================

TARGET_IP="${1:-10.0.0.10}"

echo "======================================================================"
echo " [TEST 1] Génération de trafic Web légitime (NOC)"
echo "======================================================================"
for i in {1..5}; do
  curl -s -o /dev/null -w "Requête HTTP #$i -> Code: %{http_code}\n" "http://${TARGET_IP}/" || true
done

echo ""
echo "======================================================================"
echo " [TEST 2] Simulation d'un User-Agent Malveillant / Scanner (SOC)"
echo " Déclenche une alerte Suricata dans /var/log/suricata/eve.json"
echo "======================================================================"
curl -s -A "BlackSun" "http://${TARGET_IP}/" >/dev/null || true
curl -s -A "sqlmap/1.7" "http://${TARGET_IP}/?id=1%27%20OR%20%271%27=%271" >/dev/null || true
echo "-> Requêtes malveillantes envoyées ! Vérifiez Grafana Explore (Loki) : {job=\"suricata-ids\"}"

echo ""
echo "======================================================================"
echo " [TEST 3] Scan de ports rapide Nmap (Reconnaissance Réseau)"
echo "======================================================================"
nmap -sT -p 21,22,80,443,3306 "${TARGET_IP}" || true
