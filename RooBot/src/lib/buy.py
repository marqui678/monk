"""Perform purchases of coins based on technical analysis.

Example:

        shell> invoke buy

`src/tasks.py` has a buy task that will call main of this module.

Todo:
    * This module is perfect. Are you kidding me?

"""
#Changed by AJV 01/23/2018

# core
import collections
import json
import logging
import pprint

# 3rd party
import argh
from retry import retry
from supycache import supycache
#from bittrex.bittrex import SELL_ORDERBOOK

# local
import lib.config
from .db import db
from . import mybinance

LOGGER = logging.getLogger(__name__)
"""TODO: move print statements to logging"""


SYS_INI = lib.config.System()

IGNORE_BY_IN = SYS_INI.ignore_markets_by_in
"Coins we wish to avoid"

IGNORE_BY_FIND = SYS_INI.ignore_markets_by_find
"We do not trade ETH or USDT based markets"


MAX_ORDERS_PER_MARKET = SYS_INI.max_open_trades_per_market
"""The maximum number of purchases of a coin we will have open sell orders for
is 3. Sometimes a coin will surge on the hour, but drop on the day or week.
And then surge again on the hour, while dropping on the longer time charts.
We do not want to suicide our account by continually chasing a coin with this
chart pattern. MANA did this for a long time before recovering. But we dont
need that much risk."""

MIN_PRICE = SYS_INI.min_price
"""The coin must cost 100 sats or more because any percentage markup for a
cheaper coin will not lead to a change in price."""

MIN_VOLUME = SYS_INI.min_volume
"Must have at least a certain amount of BTC in transactions over last 24 hours"

MIN_GAIN = SYS_INI.min_gain
"1-hour gain must be 5% or more"

#TODO Fix this
@retry(exceptions=json.decoder.JSONDecodeError, tries=600, delay=5)
def number_of_open_orders_in(openorders, market):
    """Maximum number of unclosed SELL LIMIT orders for a coin.

    RooBot detects hourly surges. On occasion the hourly surge is part
    of a longer downtrend, leading RooBot to buy on surges that do not
    close. We do not want to keep buying false surges so we limit ourselves to
    3 open orders on any one coin.

    Args:
        exchange (int): The exchange object.
        market (str): The coin.

    Returns:
        int: The number of open orders for a particular coin.

    """
    orders = list()
    open_orders_list = openorders['result']
    if open_orders_list:
        for order in open_orders_list:
            if order['Exchange'] == market:
                orders.append(order)

    return len(orders)


def percent_gain(new, old):
    """The percentage increase from old to new.

    Returns:
        float: percentage increase [0.0,100.0]
    """
    gain = (new - old) / old
    gain *= 100
    return gain

#Changed by AJV 01/22/2018
def obtain_btc_balance(exchange):
    """Get BTC balance.

    Returns:
        dict: The account's balance of BTC.
    """
    bal = exchange.get_asset_balance('BTC')
    return bal['result']


#Changed by AJV 01/22/2018
def available_btc(exchange):
    """Get BTC balance.

    Returns:
        float: The account's balance of BTC.
    """
    bal = obtain_btc_balance(exchange)
    avail = bal['free']
    print("\tAvailable btc={0}".format(avail))
    return avail


def record_buy(config_file, order_id, market, rate, amount):
    """Store the details of a coin purchase.

    Create a new record in the `buy` table.

    Returns:
        Nothing
    """
    db.buy.insert(
        config_file=config_file,
        order_id=order_id, market=market, purchase_price=rate, amount=amount)
    db.commit()

#TODO: Make sure that the indexes match and it returns the right rate
#Changed by AJV 01/23/2018
def rate_for(exchange, market, btc):
    "Return the rate that allows you to spend a particular amount of BTC."

    coin_amount = 0
    btc_spent = 0
    orders = exchange.get_order_book(symbol = market, limit = 1000)
    for order in orders['asks']:
        btc_spent += order[0] * order[1]
        if btc_spent > 1.4* btc:
            coin_amount = btc / order[0]
            return order[0], coin_amount
    return 0


def percent2ratio(percentage):
    """Convert a percentage to a float.

    Example:
        if percentage == 5, then return 5/100.0:

    """
    return percentage / 100.0


def calculate_trade_size(user_config):
    """How much BTC to allocate to a trade.

    Given the seed deposit and the percentage of the seed to allocate to each
    trade.

    Returns:
        float : the amount of BTC to spend on trade.
    """

    holdings = user_config.trade_deposit
    trade_ratio = percent2ratio(user_config.trade_trade)

    return holdings * trade_ratio


def get_trade_size(user_config, btc):
    "Determine how much BTC to spend on a buy."

    # Do not trade if we are configured to accumulate btc
    # (presumably for withdrawing a percentage for profits)
    if btc <= user_config.trade_preserve:
        print("BTC balance <= amount to preserve")
        return 0

    # If we have more BTC than the size of each trade, then
    # make a trade of that size
    trade_size = calculate_trade_size(user_config)
    print("\tTrade size   ={}".format(trade_size))
    if btc >= trade_size:
        return trade_size

    # Otherwise do not trade
    return 0

#Changed by AJV 01/23/2018
def fee_adjust(btc, exchange):
    """The amount of BTC that can be spent on coins sans fees.

    For instance if you want to spend 0.03BTC per trade, but the exchange charges 0.25% per trade,
    then you can spend 0.03 -  0.03 * 0.0025 instead of 0.03
    """

    #Changed exchange fee AJV 01/23/2018
    exchange_fee = 0.05 # 0.05% on Binance
    print("Adjusting {} trade size to respect {}% exchange fee on {}".format(
        btc, exchange_fee, exchange))

    exchange_fee /= 100.0

    adjusted_spend = btc - btc * exchange_fee
    return adjusted_spend


#Changed by AJV 01/23/2018
def _buycoin(config_file, user_config, exchange, market, btc):
    "Buy into market using BTC."

    size = get_trade_size(user_config, btc)

    if not size:
        print("No trade size. Returning.")
        return
    else:
        size = fee_adjust(size, exchange)

    print("I will trade {0} BTC.".format(size))

    rate, amount_of_coin = rate_for(exchange, market, size)

    print("I get {0} units of {1} at the rate of {2:.8f} BTC per coin.".format(
        amount_of_coin, market, rate))

    #TODO Critical This handles the buying. Make sure this works.
    result = exchange.order_limit_buy(symbol = market, quantity = amount_of_coin, price = rate)
    #Changed by AJV 01/23/2018
    #check to see if the following condition works
    #Replace FILLED with constant from client
    if result['status'] == "FILLED":
        print("\tBuy was a success = {}".format(result))
        record_buy(config_file, result['orderId'], market, rate, amount_of_coin)
    else:
        print("\tBuy FAILED: {}".format(result))


def buycoin(config_file, user_config, exchange, top_coins):
    "Buy top N cryptocurrencies."

    avail = available_btc(exchange)

    for market in top_coins:
        _buycoin(config_file, user_config, exchange, market[0], avail)


@supycache(cache_key='result')
def analyze_gain(exchange):
    """Find the increase in coin price.

    The market database table stores the current ask price of all coins.
    Every hour `invoke download` creates another row in this table. Then when
    `invoke buy` gets to the analyze_gain function, analyze_gain pulls the 2
    most recent rows from market and subtracts the ask prices to determine the
    1-hour price gain.

    Returns:
        list : A list of 5-tuples of this form
           (
                name,  # the market name, e.g. "BTC-NEO"
                percent_gain(row[0].ask, row[1].ask), # 1-hour price gain
                row[1].ask, # price this hour
                row[0].ask, # prince 1 hour ago
                'https://bittrex.com/Market/Index?MarketName={0}'.format(name),
            )
    """
    def should_skip(name):
        """Decide if a coin should be part of surge analysis.

        IGNORE_BY_IN filters out coins that I do not trust.
        IGNORE_BY_FIND filters out markets that are not BTC-based.
          E.g: ETH and USDT markets.
        """
        for ignorable in IGNORE_BY_IN:
            if ignorable in name:
                print("\tIgnoring {} because {} is in({}).".format(
                    name, ignorable, IGNORE_BY_IN))
                return True

        for ignore_string in IGNORE_BY_FIND:
            if name.find(ignore_string) > -1:
                print('\tIgnore by find: ' + name)
                return True

        return False

    def get_recent_market_data():
        """Get price data for the 2 time points.

        RooBot detects changes in coin price. To do so, it subtracts the
        price of the coin at one point in time versus another point in time.
        This function gets the price data for 2 points in time so the difference
        can be calculated.
        """
        #TODO Should I update this procedure to check more regularly?
        retval = collections.defaultdict(list)

        for row in db().select(db.market.ALL, groupby=db.market.name):
            for market_row in db(db.market.name == row.name).select(
                    db.market.ALL,
                    orderby=~db.market.timestamp,
                    limitby=(0, 2)
            ):
                retval[market_row.name].append(market_row)

        return retval

    markets = exchange.get_market_summaries(by_market=True)
    recent = get_recent_market_data()

    openorders = exchange.get_open_orders()

    print("<ANALYZE_GAIN numberofmarkets={0}>".format(len(list(recent.keys()))))

    gain = list()

    for name, row in recent.items():

        print("Analysing {}...".format(name))

        if len(row) != 2:
            print("\t2 entries for market required. Perhaps this is the first run?")
            continue

        if should_skip(name):
            continue

        try:
            if markets[name]['BaseVolume'] < MIN_VOLUME:
                print("\t{} 24hr vol < {}".format(markets[name], MIN_VOLUME))
                continue
        except KeyError:
            print("\tKeyError locating {}".format(name))
            continue

        if number_of_open_orders_in(openorders, name) >= MAX_ORDERS_PER_MARKET:
            print('\tToo many open orders: ' + name)
            continue

        if row[0].ask < MIN_PRICE:
            print('\t{} costs less than {}.'.format(name, MIN_PRICE))
            continue

        gain.append(
            (
                name,
                percent_gain(row[0].ask, row[1].ask),
                row[1].ask,
                row[0].ask,
                'https://bittrex.com/Market/Index?MarketName={0}'.format(name),
            )
        )

    print("</ANALYZE_GAIN>")

    gain = sorted(gain, key=lambda r: r[1], reverse=True)
    return gain


def topcoins(exchange, number_of_coins):
    """Find the coins with the greatest change in price.

    Calculate the gain of all BTC-based markets. A market is where
    one coin is exchanged for another, e.g: BTC-XRP.

    #TODO Think through the Criteria
    Markets must meet certain criteria:
        * 24-hr volume of MIN_VOLUME
        * price gain of MIN_GAIN
        * BTC-based market only
        * Not filtered out because of should_skip()
        * Cost is 125 satoshis or more

    Returns:
        list : the markets which are surging.
    """
    top = analyze_gain(exchange)

    # print 'TOP: {}.. now filtering'.format(top[:10])
    top = [t for t in top if t[1] >= MIN_GAIN]
    # print 'TOP filtered on MIN_GAIN : {}'.format(top)


    print("Top 5 coins filtered on %gain={} and volume={}:\n{}".format(
        MIN_GAIN,
        MIN_VOLUME,
        pprint.pformat(top[:5], indent=4)))

    return top[:number_of_coins]


def process(config_file):
    """Buy coins for every configured user of the bot."""
    user_config = lib.config.User(config_file)

    exchange = mybinance.make_binance(user_config.config)

    top_coins = topcoins(exchange, user_config.trade_top)

    print("------------------------------------------------------------")
    print("Buying coins for: {}".format(config_file))
    buycoin(config_file, user_config, exchange, top_coins)


def main(inis):
    """Buy coins for every configured user of the bot."""

    for config_file in inis:
        process(config_file)

if __name__ == '__main__':
    argh.dispatch_command(main)
