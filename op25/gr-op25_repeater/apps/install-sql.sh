#! /bin/sh

PIP3=`which pip3`
USERDIR=~/.local/bin

sudo apt-get install python3-pip

PIP3=`which pip3`

# # # # # # un-comment the following two lines for ubuntu 16.04 # # # # # # 
#pip3 install --user pip==10.0.1
#PIP3=$USERDIR/pip3

echo PIP3 now set to $PIP3
# # # $PIP3 --version  # # # generates errors -- (?)

$PIP3 install --user sqlalchemy 
$PIP3 install --user flask
$PIP3 install --user datatables
$PIP3 install --user flask-sqlalchemy

cd
git clone https://github.com/Pegase745/sqlalchemy-datatables.git
cd sqlalchemy-datatables
$PIP3 install --user .
cd

echo the following line must be added to your .bashrc
echo "export PATH=$USERDIR:\$PATH"

