## Python Script

## Pre-requisites
- Python >= 3.10
- PostgreSQL >= 13.4


### Create Database and User
```
sudo -u postgres psql -c "CREATE ROLE payrue WITH LOGIN PASSWORD 'payrue'"
sudo -u postgres createdb payrue -E UTF-8 --owner payrue
```
