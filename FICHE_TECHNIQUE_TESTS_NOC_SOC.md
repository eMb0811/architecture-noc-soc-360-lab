# 📋 FICHE TECHNIQUE DE RECETTE & TESTS — LABO NOC / SOC 360°

| Métadonnée | Détail |
| :--- | :--- |
| **Projet** | Architecture d'Observabilité NOC / SOC 360° (4 Couches) |
| **Machine Virtuelle Cible** | `NOC-SOC-360-Lab` (`192.168.126.100`) — Ubuntu 22.04 LTS sous VMware Workstation |
| **Accès SSH Rapide (Windows)** | `ssh -i "C:\workspace\ops\tp3-admin_reseaux\ssh\tp3_ed25519" root@192.168.126.100` *(ou mot de passe : `Passer@2026`)* |
| **Répertoire du Labo sur la VM** | `/opt/noc-soc-lab` |
| **Dépôt GitHub** | https://github.com/eMb0811/architecture-noc-soc-360-lab |

---

## 🎯 Objectif de cette Fiche Technique
Cette fiche est un **Runbook opérationnel (Cahier de Recette)**. Elle permet de tester, vérifier et démontrer (par exemple lors d'une soutenance ou d'un audit technique) le bon fonctionnement de **chacune des 4 couches** de l'architecture en 7 tests chronologiques :
1. **Test 1 :** Vérification de santé de l'infrastructure centrale (Docker Compose & Agent Alloy).
2. **Test 2 :** Vérification de la topologie réseau SDN **Mininet**, du switch **Open vSwitch (`s1`)** et du **Port Miroir (`span0`)**.
3. **Test 3 :** Vérification du cluster **Kubernetes (`Kind`)** et des microservices métiers.
4. **Test 4 :** Simulation de trafic légitime (**NOC**) et vérification des métriques dans **VictoriaMetrics**.
5. **Test 5 :** Simulation de cyberattaques (**SOC** : Injection SQL `sqlmap`, Scanner `BlackSun`, Reconnaissance `Nmap`) et vérification dans **Suricata / Loki**.
6. **Test 6 :** Investigation post-incident (**Forensics Réseau**) en SQL dans **ClickHouse**.
7. **Test 7 :** Déclenchement de l'**Alerting Grafana** et **Remédiation Active (Isolation L2/L3 de l'attaquant sur Open vSwitch)**.

---

## 🧪 TEST 1 : Vérifier le Serveur Central et le Pipeline Grafana Alloy

### 1.1 Commandes à exécuter (sur la VM en SSH)
```bash
cd /opt/noc-soc-lab/01-central-stack
docker compose ps
```

### 1.2 Résultat attendu
Les **5 conteneurs** doivent être à l'état **`Up`** :
* `noc-victoriametrics` (Port `8428`)
* `soc-loki` (Port `3100`)
* `noc-clickhouse` (Ports `8123` / `9000`)
* `noc-soc-alloy` (Port `12345`)
* `noc-soc-grafana` (Port `3000`)

### 1.3 Vérification Visuelle (Depuis le navigateur Windows)
1. Ouvrir **http://192.168.126.100:12345/graph** (Interface **Grafana Alloy**).
2. Vérifier que les **7 blocs** (`prometheus.scrape`, `prometheus.exporter.unix`, `prometheus.remote_write`, `loki.source.file`, `loki.source.docker`, `discovery.docker`, `loki.write`) affichent le badge vert **`Healthy`**.

---

## 🌐 TEST 2 : Vérifier le Réseau Mininet et le Port Miroir Open vSwitch (`span0`)

### 2.1 Commandes à exécuter (sur la VM)
Vérifier que le switch cœur `s1` et son port miroir `span0-ovs <---> span0` sont actifs :
```bash
# 1. Voir les ports branchés sur le switch Open vSwitch s1
sudo ovs-vsctl show

# 2. Vérifier que le Port Mirroring (SPAN) est actif sur s1
sudo ovs-vsctl list Mirror

# 3. Vérifier que l'interface de sonde span0 est en mode PROMISC et UP
ip -br link show span0
```

> **Si le réseau Mininet n'est pas encore lancé :**
> ```bash
> sudo nohup python3 /opt/noc-soc-lab/02-network-mininet/topology_noc_soc.py --daemon > /var/log/mininet-lab.log 2>&1 &
> ```

### 2.2 Tester la connectivité interne entre les hôtes Mininet
Récupérer le PID du *Network Namespace* de la machine `h3_atk` (`10.0.0.99`) et pinger le serveur Web `h1_web` (`10.0.0.10`) et la base `h2_db` (`10.0.0.20`) :
```bash
H3_PID=$(pgrep -f "mininet:h3_atk" | head -n1)
sudo mnexec -a $H3_PID ping -c 2 10.0.0.10
sudo mnexec -a $H3_PID ping -c 2 10.0.0.20
```
* **Résultat attendu :** `0% packet loss` sur les deux cibles.

### 2.3 Preuve que le Port Miroir (`span0`) duplique bien les paquets
Dans le terminal de la VM, écouter 4 paquets sur `span0` pendant un ping entre `h3_atk` et `h1_web` :
```bash
sudo mnexec -a $H3_PID ping -c 2 10.0.0.10 >/dev/null &
sudo tcpdump -i span0 -n icmp -c 4
```
* **Résultat attendu :** `tcpdump` sur `span0` affiche `IP 10.0.0.99 > 10.0.0.10: ICMP echo request` et `echo reply`. Cela prouve que le switch copie 100 % du trafic vers la sonde !

---

## ☸️ TEST 3 : Vérifier le Cluster Kubernetes (`Kind`) et l'Application Métier

### 3.1 Commandes à exécuter (sur la VM)
```bash
# 1. Vérifier l'état du noeud Kubernetes
kubectl get nodes -o wide

# 2. Vérifier que tous les Pods (Système + Application intranet-web) tournent
kubectl get pods -A

# 3. Tester l'application web exposée par Kubernetes (NodePort 30080 -> Port 8080)
curl -I http://localhost:8080
```

### 3.2 Résultat attendu
* Le nœud `noc-soc-k8s-control-plane` est **`Ready`**.
* Les 2 réplicas `intranet-web-...` sont **`1/1 Running`**.
* La commande `curl -I http://localhost:8080` renvoie **`HTTP/1.1 200 OK`** (`Server: nginx/1.27`).

---

## 📈 TEST 4 : Générer du Trafic NOC et Vérifier les Métriques (VictoriaMetrics)

### 4.1 Générer une charge HTTP légitime vers le Serveur Web (`10.0.0.10`) et Kubernetes (`:8080`)
```bash
H3_PID=$(pgrep -f "mininet:h3_atk" | head -n1)
for i in {1..20}; do
  sudo mnexec -a $H3_PID curl -s http://10.0.0.10/ >/dev/null
  curl -s http://localhost:8080/ >/dev/null
done
echo "20 requêtes Web générées avec succès !"
```

### 4.2 Vérification dans VictoriaMetrics (Ligne de commande ou Navigateur)
* **En ligne de commande (API PromQL) :**
  ```bash
  curl -s 'http://localhost:8428/api/v1/query?query=node_memory_MemAvailable_bytes' | jq '.data.result[0].value'
  ```
* **Dans le navigateur :** Ouvrir **http://192.168.126.100:8428/vmui** et exécuter :
  ```promql
  rate(node_network_receive_bytes_total{device=~"span0|s1.*|eth0"}[1m])
  ```

---

## 🚨 TEST 5 : Simuler les Cyberattaques (SOC) et Vérifier Suricata IDS + Loki

### 5.1 Vérifier que la sonde Suricata écoute bien sur `span0`
```bash
ps aux | grep suricata
```
*(Si Suricata n'est pas lancé : `sudo suricata -i span0 -k none -S /etc/suricata/noc-soc-lab.rules -D`)*

### 5.2 Lancer le Script d'Attaque depuis l'Hôte Attaquant `h3_atk` (`10.0.0.99`)
```bash
H3_PID=$(pgrep -f "mininet:h3_atk" | head -n1)
sudo mnexec -a $H3_PID bash /opt/noc-soc-lab/04-sonde-ids/simulate_attacks.sh 10.0.0.10
```
Ce script exécute automatiquement :
1. **Un scan de vulnérabilités avec User-Agent malveillant `BlackSun`**.
2. **Une attaque par Injection SQL (`sqlmap/1.7` : `/?id=1' OR '1'='1`)**.
3. **Un scan de ports `Nmap` sur les ports `21 (FTP)`, `22 (SSH)`, `80 (HTTP)`, `443 (HTTPS)`, `3306 (MySQL)`**.

### 5.3 Vérifier la détection immédiate par Suricata (Fichier local & Grafana Loki)
* **Dans le terminal de la VM :**
  ```bash
  sudo tail -n 10 /var/log/suricata/fast.log
  ```
  **Résultat attendu :**
  ```text
  [**] [1:9900001:1] [SOC-CRITICAL] Detection Scanner Malveillant BlackSun [**] {TCP} 10.0.0.99 -> 10.0.0.10:80
  [**] [1:9900002:1] [SOC-CRITICAL] Tentative Injection SQL (sqlmap detecte) [**] {TCP} 10.0.0.99 -> 10.0.0.10:80
  [**] [1:9900003:1] [SOC-RECON] Scan de Port FTP (Nmap) [**] {TCP} 10.0.0.99 -> 10.0.0.10:21
  [**] [1:9900004:1] [SOC-RECON] Scan de Port MySQL (Nmap) [**] {TCP} 10.0.0.99 -> 10.0.0.10:3306
  ```
* **Dans Grafana (http://192.168.126.100:3000/d/noc-soc-360-main) :**
  Le panneau **« 🚨 Détections d'Attaques Suricata IDS en Temps Réel »** affiche les lignes d'alerte formatées avec la sévérité, l'IP attaquante `10.0.0.99` et la cible `10.0.0.10`.

---

## 🕵️ TEST 6 : Investigation Forensics Réseau dans ClickHouse

### 6.1 Synchroniser et interroger la base analytique ClickHouse (`ntopng.flows`)
```bash
# Insérer les nouveaux flux capturés sur span0 dans ClickHouse
jq -r 'select(.in_iface=="span0" and (.event_type=="flow" or .event_type=="alert")) | [
  (.timestamp | split(".")[0] | gsub("T"; " ")),
  .in_iface, .src_ip, (.src_port // 0), .dest_ip, (.dest_port // 0),
  .proto, (.app_proto // "l4"), (.flow.pkts_toserver // 1), (.flow.bytes_toserver // 64),
  (.flow.pkts_toclient // 0), (.flow.bytes_toclient // 0),
  (if .event_type=="alert" then .alert.signature else "TRAFIC_NORMAL" end)
] | @tsv' /var/log/suricata/eve.json | docker exec -i noc-clickhouse clickhouse-client --query="INSERT INTO ntopng.flows FORMAT TabSeparated"

# Exécuter une requête d'audit Forensics SQL dans ClickHouse
docker exec noc-clickhouse clickhouse-client -q "
SELECT
    src_ip AS Attaquant,
    dest_ip AS Cible,
    dest_port AS Port_Vise,
    proto AS Protocole,
    security_status AS Qualification_SOC,
    count() AS Nb_Evenements,
    sum(bytes_toserver) AS Volume_Octets
FROM ntopng.flows
WHERE src_ip = '10.0.0.99'
GROUP BY src_ip, dest_ip, dest_port, proto, security_status
ORDER BY Nb_Evenements DESC
FORMAT PrettyCompact
"
```

### 6.2 Résultat attendu
ClickHouse affiche un tableau synthétique regroupant toutes les actions de l'attaquant `10.0.0.99` par port visé (`80`, `21`, `3306`) et par type d'attaque.

---

## 🛡️ TEST 7 : Tester l'Alerting Grafana & la Remédiation Active (Blocage de l'Attaquant)

### 7.1 Vérifier le déclenchement des Règles d'Alerte dans Grafana
1. Ouvrir **http://192.168.126.100:3000/alerting/list?view=list**
2. Vérifier la présence des 3 règles provisionnées dans le dossier **`Alertes NOC-SOC 360`** :
   * `[SOC-CRITICAL] Intrusion Réseau Détectée par Suricata IDS (Port Miroir span0)`
   * `[NOC-WARNING] Saturation CPU Serveur / Cluster Kind (> 85%)`
   * `[NOC-WARNING] Consommation Mémoire RAM Critique (> 90%)`

### 7.2 Appliquer la Remédiation Active (Bannissement OpenFlow de l'Attaquant `10.0.0.99`)
Pour démontrer comment le SOC bloque l'attaquant sur le switch **Open vSwitch (`s1`)** suite à l'alerte :

```bash
# 1. Injecter une règle OpenFlow de priorité 500 sur le switch s1 qui bloque toute trame IP venant de 10.0.0.99
sudo ovs-ofctl add-flow s1 "priority=500,ip,nw_src=10.0.0.99,actions=drop"

# 2. Vérifier que la règle de blocage est active dans la table OpenFlow du switch s1
sudo ovs-ofctl dump-flows s1

# 3. Tester depuis l'attaquant h3_atk (10.0.0.99) : il est désormais totalement isolé !
H3_PID=$(pgrep -f "mininet:h3_atk" | head -n1)
sudo mnexec -a $H3_PID ping -c 2 -W 1 10.0.0.10 || echo "BLOQUÉ PAR LE SOC : 100% Packet Loss !"

# 4. Vérifier que le serveur de base de données h2_db (10.0.0.20), lui, peut toujours joindre h1_web (10.0.0.10) !
H2_PID=$(pgrep -f "mininet:h2_db" | head -n1)
sudo mnexec -a $H2_PID ping -c 2 10.0.0.10
```

* **Résultat attendu :**
  * `h3_atk` (`10.0.0.99`) subit **100 % de perte de paquets** (`BLOQUÉ PAR LE SOC`).
  * `h2_db` (`10.0.0.20`) continue de communiquer normalement avec `h1_web` (`0% packet loss`).

### 7.3 Lever la quarantaine (Retour à la normale après test)
```bash
sudo ovs-ofctl del-flows s1 "ip,nw_src=10.0.0.99"
```

---

## ✅ Grille Récapitulative de Validation (Checklist Soutenance / Audit)

| # | Test de Recette | Couche | Critère de Succès | Statut |
| :-: | :--- | :---: | :--- | :---: |
| **1** | Santé des 5 conteneurs & Pipeline Alloy | Couches 2, 3, 4 | 5 conteneurs `Up` + 7 composants Alloy `Healthy` | ✅ Validé |
| **2** | Topologie Mininet & Port Miroir `span0` | Couche 1 | Ping `0% loss` + `tcpdump -i span0` voit le trafic | ✅ Validé |
| **3** | Cluster Kubernetes `Kind` (`noc-soc-k8s`) | Couche 1 | Nœud `Ready` + 2 Pods `intranet-web` `Running` (`200 OK`) | ✅ Validé |
| **4** | Collecte Métriques NOC (VictoriaMetrics) | Couche 3 | Courbes CPU, RAM et Débit visibles dans VMUI & Grafana | ✅ Validé |
| **5** | Détection IDS Temps Réel (Suricata + Loki) | Couches 2 & 3 | Alertes `sqlmap`, `BlackSun` et `Nmap` visibles dans Grafana | ✅ Validé |
| **6** | Investigation Forensics SQL (ClickHouse) | Couche 3 | Requête SQL `ntopng.flows` agrège les attaques de `10.0.0.99` | ✅ Validé |
| **7** | Alerting & Isolation OpenFlow de l'attaquant | Couche 4 & 1 | Règles provisionnées + `10.0.0.99` bloqué sans impacter `10.0.0.20` | ✅ Validé |
