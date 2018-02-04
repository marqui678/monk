#Reviewed by AJV 02/03/2018
#Changed by AJV 01/22/2018

# core
import ConfigParser

# 3rd party
import argh

# local
from db import db
import mybinance


def calc_profits(exchange, config):
    import datetime
    now = datetime.datetime.now()
    print now
    now = now.replace(hour=0, minute=0, second=0, microsecond=0)
    print now

    cutoff_time = now - datetime.timedelta(1)
    print cutoff_time
    rows = db(db.buy.timestamp >= cutoff_time).select()
    print rows

def process(config_file):
    config = ConfigParser.RawConfigParser()
    config.read(config_file)

    exchange = mybinance.make_binance(config)

    calc_profits(exchange, config)

def main(ini):

    process(ini)

if __name__ == '__main__':
    argh.dispatch_command(main)
