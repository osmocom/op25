#! /bin/sh

if [ ! -f $PWD/blacklist-rtl.conf ]; then
	echo "error, you must change to the op25/scripts directory prior to running this script"
	exit 1
fi

# blacklist rtl dtv drivers
if [ ! -f /etc/modprobe.d/blacklist-rtl.conf ]; then
        echo ====== installing blacklist-rtl.conf
        echo ====== please reboot before running op25
        sudo install -m 0644 ./blacklist-rtl.conf /etc/modprobe.d/
fi

# fix borked airspy udev rule to allow used of airspy device when running headless
if [ -f /lib/udev/rules.d/60-libairspy0.rules ]; then
    echo ====== fixing libairspy0 udev rule
        echo ====== please reboot before running op25
    sudo sed -i 's^TAG+="uaccess"^MODE="660", GROUP="plugdev"^g' /lib/udev/rules.d/60-libairspy0.rules
fi
