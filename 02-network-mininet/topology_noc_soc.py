#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
COUCHE 1 & 2 : TOPOLOGIE RÉSEAU MININET AVEC PORT MIROIR (SPAN) OPEN VSWITCH
==============================================================================
Objectif pédagogique :
Au lieu d'utiliser OpenStack (trop lourd pour 2 coeurs CPU), ce script utilise
Mininet et Open vSwitch (le même moteur réseau que Neutron dans OpenStack) pour :
  1. Créer un switch coeur d'entreprise (s1)
  2. Connecter 3 machines virtuelles légères (Network Namespaces) :
     - h1_web (10.0.0.10/24) : Serveur Web de production
     - h2_db  (10.0.0.20/24) : Serveur Base de données
     - h3_atk (10.0.0.99/24) : Machine attaquante (Kali/Pentest simulé)
       Note pédagogique : sous Linux (IFNAMSIZ), un nom d'interface réseau est
       limité à 15 caractères max ('h3_atk-eth0' = 11 caractères).
  3. Créer une interface virtuelle 'span0' sur la VM Ubuntu et configurer un
     vrai PORT MIROIR (SPAN) sur le switch s1 pour que Suricata et ntopng
     voient 100% du trafic qui circule entre h1, h2 et h3 !
==============================================================================
"""

import os
import time
from mininet.net import Mininet
from mininet.node import OVSSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel, info


def configure_ovs_span_mirror(switch_name="s1", span_iface="span0"):
    """
    Configure un Port Miroir (SPAN) sur le switch Open vSwitch (s1).
    Tout le trafic entrant/sortant de s1 est dupliqué vers l'interface 'span0'
    où écoutent Suricata (IDS) et ntopng (DPI).
    """
    info("\n*** [NOC/SOC] Création du câble virtuel SPAN (veth pair : span0-ovs <---> span0)...\n")
    # Nettoyage si l'interface existe déjà d'un test précédent
    os.system(f"ip link del {span_iface} 2>/dev/null")

    # Explication pédagogique :
    # On crée une paire d'interfaces reliées comme un vrai câble RJ45 (veth pair) :
    # - 'span0-ovs' est branché sur le port miroir du switch Open vSwitch (s1)
    # - 'span0' reçoit tous les paquets en réception (RX) pour Suricata et ntopng !
    os.system(f"ip link add {span_iface} type veth peer name {span_iface}-ovs")
    os.system(f"ip link set {span_iface} up promisc on")
    os.system(f"ip link set {span_iface}-ovs up promisc on")

    info(f"*** [NOC/SOC] Branchement de {span_iface}-ovs sur le switch OVS {switch_name}...\n")
    os.system(f"ovs-vsctl --may-exist add-port {switch_name} {span_iface}-ovs")

    info(f"*** [NOC/SOC] Activation du Port Mirroring (SPAN) intégral vers {span_iface}...\n")
    mirror_cmd = (
        f"ovs-vsctl "
        f"-- --id=@p get port {span_iface}-ovs "
        f"-- --id=@m create mirror name=soc-span-mirror select-all=true output-port=@p "
        f"-- set bridge {switch_name} mirrors=@m"
    )
    os.system(mirror_cmd)
    info("*** [NOC/SOC] Port Miroir actif ! Suricata et ntopng écoutent en RX sur 'span0'.\n")


def run_noc_soc_topology():
    # Création du réseau sans contrôleur externe (switchs en mode standalone L2)
    net = Mininet(switch=OVSSwitch, controller=None)

    info("*** 1. Création du Switch Coeur Open vSwitch (s1)...\n")
    s1 = net.addSwitch("s1", failMode="standalone")

    info("*** 2. Création des Hôtes du Labo...\n")
    h1_web = net.addHost("h1_web", ip="10.0.0.10/24")
    h2_db = net.addHost("h2_db", ip="10.0.0.20/24")
    h3_atk = net.addHost("h3_atk", ip="10.0.0.99/24")

    info("*** 3. Câblage virtuel des hôtes sur le switch s1...\n")
    net.addLink(h1_web, s1)
    net.addLink(h2_db, s1)
    net.addLink(h3_atk, s1)

    info("*** 4. Démarrage de la topologie Mininet...\n")
    net.start()

    # Configuration du Port Miroir (SPAN) vers span0
    configure_ovs_span_mirror(switch_name="s1", span_iface="span0")

    info("*** 5. Démarrage d'un serveur Web HTTP sur h1_web (10.0.0.10:80)...\n")
    h1_web.cmd("python3 -m http.server 80 >/tmp/h1_http.log 2>&1 &")
    time.sleep(1)

    info("\n======================================================================\n")
    info(" LABO RÉSEAU NOC/SOC PRÊT !\n")
    info(" - Serveur Web (h1_web) : 10.0.0.10 (Port 80 ouvert)\n")
    info(" - Serveur DB  (h2_db)  : 10.0.0.20\n")
    info(" - Attaquant   (h3_atk) : 10.0.0.99\n")
    info(" - Sonde SPAN           : interface 'span0' (hôte Ubuntu)\n")
    info("----------------------------------------------------------------------\n")
    info(" Commandes de test à taper dans le prompt 'mininet>' ci-dessous :\n")
    info("   1) Tester la connectivité : pingall\n")
    info("   2) Générer du trafic Web  : h3_atk curl http://10.0.0.10\n")
    info("   3) Simuler une attaque SQL: h3_atk curl \"http://10.0.0.10/?id=1' OR '1'='1\"\n")
    info("   4) Simuler un scan Nmap   : h3_atk nmap -sS 10.0.0.10\n")
    info("======================================================================\n\n")

    if "--daemon" in os.sys.argv:
        info("*** Mode Daemon actif : le réseau Mininet et le port miroir 'span0' tournent en arrière-plan.\n")
        try:
            while True:
                time.sleep(5)
        except KeyboardInterrupt:
            pass
    else:
        CLI(net)

    info("*** Arrêt du labo et nettoyage de l'interface span0...\n")
    os.system("ovs-vsctl clear bridge s1 mirrors 2>/dev/null")
    os.system("ip link del span0 2>/dev/null")
    net.stop()


if __name__ == "__main__":
    setLogLevel("info")
    run_noc_soc_topology()
