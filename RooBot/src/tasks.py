#Reviewed by AJV 02/03/2018
"""Define a collection of tasks invokable from the command-line/cron.

This module leverages `PyInvoke`_ to create tasks relevant ot the execution
of RooBot. The tasks are ordered in this module in the order that you
would typically use them:
    1. you would download the market data via `invoke download`
    1. The next hour you would download the market data again.
    1. Then `invoke buy` to buy the coins with the strongest gain.
    1. Then `invoke takeprofit` to set profit targets for your buys.
    1. Then `invoke profitreport -d yesterday` to see what profits you made
    1. Then `invoke cancelsells` to cancel all sell orders so that
    `invoke takeprofit` then re-issue them.
    1. On rare occassions, you might liquidate all coins in your portfolio,
    cancelling all open sell orders. This is usually done when you are
    restarting / abandoning RooBot usage.

Example:

        $ invoke download

Todo:
    * For module TODOs
    * You have to also use ``sphinx.ext.todo`` extension

.. _PyInvoke:
   http://www.pyinvoke.org/
"""

# core
import logging
import random

# 3rd party
from invoke import task

#local
import lib.config
import lib.logconfig
import lib.report.profit
import lib.takeprofit



#TODO
SYS_INI = lib.config.System()

LOG = logging.getLogger('app')


def listify_ini(ini, randomize=False):
    """Coerce the ini argument to a list of 1+ ini-file names.

    When provided with a value V, return a list consisting solely of V.
    When no value is provided, return a list consisting of the ini files of
    all active users:

    Args:
        ini (str): The name of an ini file or a falsy value.

    Returns:
        A list of 1+ ini-file names

    """
    if ini:
        inis = [ini]
    else:
        inis = SYS_INI.users_inis
        if randomize:
            random.shuffle(inis)

    return inis

@task
def download(_ctx):
    """Download the current price data for all markets on Binance.

    Call getmarketsummaries via `the Binance API`_ and place the JSON
    file in src/tmp.

    Args:
        None other than the PyInvoke context object.

    Returns:
        Nothing.

    .. _the Binance API:
        https://api.binance.com/api/v1/

    """
    from lib import download as _download

    _download.main(random.choice(SYS_INI.users_inis))


@task
def buy(_ctx, ini=None):
    """Analyze market data (obtained via `invoke download`) and buy coins.

    Buy compares last hour's market data with this hour and find the coin(s)
    that have shown the most growth in an hour. It filters out certain coins
    based on certain criteria. And then buy the top N coin(s).

    Returns:
        Nothing.
    """
    from lib import buy as _buy

    inis = listify_ini(ini, randomize=False)
    _buy.main(inis)


@task
def takeprofit(_ctx, ini=None):
    """Issue SELL LIMIT orders on the coin(s) that have been bought.

    Every 5 minutes this task runs to see if any new coins have been bought.
    If so, it then sets a profit target for them.
    """

    inis = listify_ini(ini)

    for _ in inis:
        LOG.debug("Processing {}".format(_))
        lib.takeprofit.take_profit(_)

@task
def profitreport(_ctx, ini=None, date_string=None, skip_markets=None):
    """Generate and email a profit report for a certain time frame.

    Args:
        ini (str): The name of an ini file or a falsy value.
        date_string : "yesterday" and "lastmonth" are valid values
        skip_markets: Coins to exclude from calculating the profit report.
            This is used when a market is under maintenance becauase at that
            point the exchange API does not return data for that coin.

    Returns:
        Nothing. It dumps a csv and html of the email profit report in src/tmp.

    """

    inis = listify_ini(ini)

    if date_string:
        from datetime import date
        if date_string == 'yesterday':
            date_string = "Yesterday"
            _date = date.fromordinal(date.today().toordinal()-1)
        elif date_string == 'lastmonth':
            date_string = "Last month"
            from dateutil.relativedelta import relativedelta
            today = date.today()
            diff = today - relativedelta(months=1)
            start_of_last_month = date(diff.year, diff.month, 1)
            end_of_last_month = date(today.year, today.month, 1) - relativedelta(days=1)
            print("Date range for profit report. Start={}. End={}".format(
                start_of_last_month, end_of_last_month))
            _date = [start_of_last_month, end_of_last_month]
        else:
            raise Exception("Unrecognized date option")
    else:
        _date = None

    if skip_markets:
        skip_markets = skip_markets.split()

    for user_ini in inis:
        LOG.debug("Processing {}".format(user_ini))
        lib.report.profit.main(user_ini, date_string, _date=_date, skip_markets=skip_markets)



@task
def cancelsells(_ctx, ini=None):
    """Cancel sell orders so that `invoke takeprofit` can re-issue them.

    Binance implemented a policy where a SELL LIMIT order can only be active
    for 28 days. After that, they close the order. The purpose of this code is
    to cancel and re-issue the order so that it remains active as long as
    necessary to close for a profit.
    """
    inis = listify_ini(ini)

    for _ in inis:
        LOG.debug("Processing {}".format(_))
        lib.takeprofit.clear_profit(_)

@task
def cancelsellid(_ctx, order_id):
    """Cancel a sell order in the rdbms table.

    If for some reason `invoke cancelsells` misses re-issuing an open transaction,
    then you can cancel a specific transaction by providing the `buy.sell_id`
    column value in the rdbms table buy.
    """


    _, exchange = lib.takeprofit.prep(SYS_INI.any_users_ini)

    lib.takeprofit.clear_order_id(exchange, order_id)

@task
def sellall(_ctx, ini):
    """Sell all coins in wallet.

    Occasionally you may need to liquidate all non-BTC coins in your wallet.
    For instance, if you want to restart RooBot. This task does that.

    Args:
        ini (str): the ini file that connects to the account to liquidate.
    """
    from lib import sellall as _sellall

    _sellall.main(ini)

@task
def openorders(_ctx, ini):
    """List the open orders for a particular user..


    """

    _, exchange = lib.takeprofit.prep(ini)

    open_orders = exchange.get_open_orders()
    for order in open_orders['result']:
        print(order)


@task
def orderhistory(_ctx, ini, market):
    """List the order history of a user for a market, e.g: BTC-NLG.


    """

    _, exchange = lib.takeprofit.prep(ini)

    records = exchange.get_order_history(market)
    for record in records['result']:
        print(record)


@task
def getorder(_ctx, ini, market, orderId):
    """Get  order details


    """

    _, exchange = lib.takeprofit.prep(ini)

    _ = exchange.get_order(symbol = market, orderId = uuid)
    print(_)