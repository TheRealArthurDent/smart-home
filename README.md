# smart-home
Setup for the smart home environment containing mqtt, iobroker and peripherals

### local setup

1. Create the file /etc/docker/smart-home/.env and fill it with the following content:
```
INFLUXDB_ADMIN_PASSWORD=admin
INFLUXDB_GRAFANA_PASSWORD=grafana
INFLUXDB_IOBROKER_PASSWORD=iobroker

GRAFANA_USERNAME=grafana
GRAFANA_PASSWORD=grafana
```

2. Create the folder 
3. Execute 'bash run.sh'
4. Be happy