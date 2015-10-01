import urllib2
import zipfile
import datetime
import pandas as pd
import pandas.io.data as web
from pandas import read_csv
from StringIO import StringIO
from nowtrade import logger

class NoDataException(Exception): pass

class DataConnection(object):
    def __init__(self):
        self.logger = logger.Logger(self.__class__.__name__)
        self.logger.info('Initialized')

    def __str__(self): return self.__class__.__name__

class YahooConnection(DataConnection):
    """
    Utilizes Pandas' Remote Data Access methods to fetch
    symbol data from Yahoo.
    """
    def get_data(self, symbol, start, end, symbol_in_column=True):
        """
        @type symbol: string
        @type start: datetime
        @type end: datetime
        @return: Returns a pandas DataFrame of the requested symbol
        @rtype: pandas.DataFrame
        """
        ret = web.DataReader(str(symbol).upper(), 'yahoo', start, end)
        ret.rename(columns=lambda name: '%s_%s' %(symbol, name), inplace=True)
        return ret

class GoogleConnection(DataConnection):
    """
    Utilizes Pandas' Remote Data Access methods to fetch
    symbol data from Google.
    """
    def _request(self, url):
        """
        Used for custom request outside of Pandas framework.
        """
        try:
            return urllib2.urlopen(url)
        except urllib2.HTTPError, e:
            print 'Error when connecting to Google servers: %s' %e
        except IOError:
            print 'Could not connect to Google servers with url %s: %s' %(url, e)
        except Exception, e:
            print 'Unknown Error when trying to connect to Google servers: %s' %e

    def get_data(self, symbol, start, end, symbol_in_column=True):
        """
        @type symbol: string
        @type start: datetime
        @type end: datetime
        @return: Returns a pandas DataFrame of the requested symbol
        @rtype: pandas.DataFrame
        """
        ret = web.DataReader(str(symbol).upper(), 'google', start, end)
        if symbol_in_column: ret.rename(columns=lambda name: '%s_%s' %(symbol, name), inplace=True)
        return ret

    def get_ticks(self, symbol, period='15d', interval=60, symbol_in_column=True):
        """
        Always returns 15 days worth of 1min data.
        Get tick prices for the given ticker symbol.
        @param symbol: symbol symbol
        @type symbol: string
        """
        symbol = str(symbol).upper()
        data = None # Return data
        #try:
        if True:
            url = 'http://www.google.com/finance/getprices?i=%s&p=%s&f=d,o,h,l,c,v&q=%s' %(interval, period, symbol)
            #try:
            page = self._request(url)
            #except Exception, e:
                #print 'Failed getting data for %s: %s' %(symbol, e)
            entries = page.readlines()[7:] # first 7 line is document information
            days = [] # Keep track of all days
            day = None # Keep track of current day
            dt = None # Keep track of current time
            # sample values:'a1316784600,31.41,31.5,31.4,31.43,150911'
            for entry in entries:
                quote = entry.strip().split(',')
                if quote[0].startswith('a'): # Datetime
                    day = datetime.datetime.fromtimestamp(int(quote[0][1:]))
                    days.append(day)
                    dt = day
                else:
                    dt = day + datetime.timedelta(minutes=int(quote[0])*interval/60)
                if symbol_in_column: df = pd.DataFrame({'%s_Open' %symbol: float(quote[4]), '%s_High' %symbol: float(quote[2]), '%s_Low' %symbol: float(quote[3]), '%s_Close' %symbol: float(quote[1]), '%s_Volume' %symbol: int(quote[5])}, index=[dt])
                else: df = pd.DataFrame({'Open': float(quote[4]), 'High': float(quote[2]), 'Low': float(quote[3]), 'Close': float(quote[1]), 'Volume': int(quote[5])}, index=[dt])
                if data is None:
                    data = df
                else: data = data.combine_first(df)
            # Reindex for missing minutes
            new_index = None
            for d in days:
                index = pd.date_range(start=d, periods=391, freq='1Min')
                if new_index is None: new_index = index
                else: new_index = new_index + index
            # Front fill for minute data
            return data.reindex(new_index, method='ffill')
        #except BaseException, e:
            #print 'Unknown Error when fetching Google tick data for %s: %s' %(symbol, e)

class OandaConnection(DataConnection):
    def __init__(self, account_id, access_token, environment='practice'):
        import oandapy
        self.account_id = account_id
        self.environment = environment
        self.oanda = oandapy.API(environment=environment, access_token=access_token)
        self.logger = logger.Logger('OandaConnection')
        self.logger.info('Initialized OandaConnection %s environment with account ID: %s' %(environment, account_id))
    def __str__(self): return 'OandaConnection(account_id=%s, access_token=******, environment=%s)' %(self.account_id, self.environment)
    def __repr__(self): return 'OandaConnection(account_id=%s, access_token=******, environment=%s)' %(self.account_id, self.environment)

    def get_data(self, symbol, granularity='H1', periods=5000, realtime=False, symbol_in_column=True):
        self.logger.info('Getting %s candles of %s data for %s granularity (realtime=%s, symbol_in_column=%s)' %(periods, symbol, granularity, realtime, symbol_in_column))
        candles = self.oanda.get_history(account_id=self.account_id, instrument=symbol, granularity=granularity, count=periods)['candles']
        if not realtime: candles.pop()
        data = None
        for candle in candles:
            dt = datetime.datetime.strptime(candle['time'], "%Y-%m-%dT%H:%M:%S.000000Z")
            if symbol_in_column: df = pd.DataFrame({'%s_Open' %symbol: candle['openBid'], '%s_High' %symbol: candle['highBid'], '%s_Low' %symbol: candle['lowBid'], '%s_Close' %symbol: candle['closeBid'], '%s_Volume' %symbol: candle['volume']}, index=[dt])
            else: df = pd.DataFrame({'Open' %symbol: candle['openBid'], 'High' %symbol: candle['highBid'], 'Low' %symbol: candle['lowBid'], 'Close' %symbol: candle['closeBid'], 'Volume' %symbol: candle['volume']}, index=[dt])
            if data is None: data = df
            else: data = data.combine_first(df)
        self.logger.debug('Data: %s' %data)
        return data

class ForexiteConnection(DataConnection):
    """
    Forexite 1min data
    """
    URL = "http://www.forexite.com/free_forex_quotes/%s/%s/%s%s%s.zip"
    #URL = "http://www.forexite.com/free_forex_quotes/YY/MM/DDMMYY.zip"
    def get_data(self, start, end):
        """
        Always returns 1min OPEN, HIGH, LOW, CLOSE for all available currency
        pairs on the Forexite website.  No Volume information.
        """
        assert start <= end
        data = {}
        # One day at a time
        while start <= end:
            day = str(start.day)
            if len(day) == 1: day = '0%s' %day
            month = str(start.month)
            if len(month) == 1: month = '0%s' %month
            long_year = str(start.year)
            year = long_year[2:]
            url = self.URL %(long_year, month, day, month, year)
            start = start + datetime.timedelta(1)
            try: page = urllib2.urlopen(url)
            except urllib2.HTTPError, e:
                print e
                continue
            try:
                zipf = zipfile.ZipFile(StringIO(page.read()))
                d = read_csv(zipf.open('%s%s%s.txt' %(day, month, year)), parse_dates=True)
            except Exception, e:
                print 'No data for %s' %url
                continue
            for ticker in d['<TICKER>'].unique():
                df = d.loc[d['<TICKER>'] == ticker]
                first_row = df.iloc[0]
                start_date = first_row['<DTYYYYMMDD>']
                start_time = first_row['<TIME>']
                df.index = pd.date_range(str(start_date) + ' ' + str(start_time).zfill(6), periods=len(df), freq='1Min')
                del df['<TICKER>']
                del df['<DTYYYYMMDD>']
                del df['<TIME>']
                df.rename(columns=lambda name: '%s_%s' %(ticker, name.strip('<>').capitalize()), inplace=True)
                if ticker in data: data[ticker] = data[ticker].combine_first(df)
                else: data[ticker] = df
        return data

class MongoDatabaseConnection(DataConnection):
    """
    MongoDB connection to retrieve data.
    """
    def __init__(self, host='127.0.0.1', port=27017, database='symbol-data', username=None, password=None):
        from pymongo import Connection
        self.connection = None
        self.db = None
        self.host = host
        self.port = port
        self.database = database
        self.username = username
        self.password = password
        try:
            self.connection = Connection(host, port)
            self.db = self.connection[database]
        except Exception as e:
            print 'Invalid database settings, ensure you run readyDatabase() with proper settings before using getData(): %s' %e

    def get_data(self, symbol, start, end, symbol_in_column=True):
        from pymongo import ASCENDING
        symbol = str(symbol).upper()
        results = self.db[symbol].find({'_id': \
                              {'$gte': start, '$lte': end}}\
                              ).sort('datetime', ASCENDING)
        ret = pd.DataFrame.from_dict(list(results))
        if len(ret) < 1: raise NoDataException()
        ret.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume', 'adj_close': 'Adj Close', '_id': 'Date'}, inplace=True)
        ret = ret.set_index('Date')
        if symbol_in_column: ret.rename(columns=lambda name: '%s_%s' %(symbol, name), inplace=True)
        return ret

    def set_data(self, data_frame, symbols, volume=True, adj_close=True):
        """
        Stores Open, Close, High, Low, Volume, and Adj Close of
        symbols specified using the data in the DataFrame provided.
        Typically you'd pull data using another connection and
        feed it's data_frame to this function in order to store
        the data in a local MongoDB.
        """
        for symbol in symbols:
            symbol = str(symbol).upper()
            output = []
            if adj_close:
                data = data_frame.loc[:, ['%s_Open' %symbol, '%s_Close' %symbol, '%s_High' %symbol, '%s_Low' %symbol, '%s_Volume' %symbol, '%s_Adj Close' %symbol]]
                data.columns = ['open', 'close', 'high', 'low', 'volume', 'adj_close']
            elif volume:
                data = data_frame.loc[:, ['%s_Open' %symbol, '%s_Close' %symbol, '%s_High' %symbol, '%s_Low' %symbol, '%s_Volume' %symbol]]
                data.columns = ['open', 'close', 'high', 'low', 'volume']
            else:
                data = data_frame.loc[:, ['%s_Open' %symbol, '%s_Close' %symbol, '%s_High' %symbol, '%s_Low' %symbol]]
                data.columns = ['open', 'close', 'high', 'low']
            for row in data.iterrows():
                values = dict(row[1])
                values['_id'] = row[0]
                self.db[symbol].insert(values)

def populate_mongo_day(symbols, start, end, db='symbol-data'):
    """
    Helper function to populate a local mongo db with daily stock data.
    Uses the YahooConnection class.
    """
    mgc = MongoDatabaseConnection(database=db)
    for symbol in symbols:
        symbol = symbol.upper()
        yc = YahooConnection()
        try:
            data = yc.get_data(symbol, start, end)
            mgc.set_data(data, [symbol])
        except Exception, e:
            print 'Error for %s (%s - %s): %s' %(symbol, start, end, e)

def populate_mongo_minute(symbols, period='15d', db='symbol-data-1min'):
    """
    Helper function to populate a local mongo db with minute stock data.
    Uses the GoogleConnection class.
    """
    mgc = MongoDatabaseConnection(database=db)
    for symbol in symbols:
        gc = GoogleConnection()
        try:
            data = gc.get_ticks(symbol, period=period)
            mgc.set_data(data, [symbol], adj_close=False)
        except Exception, e:
            print 'Failed %s: %s' %(symbol, e)

def populate_currency_minute(start, end, sleep=None, db='symbol-data-1min-currency'):
    """
    Helper function to populate a local mongo db with currency minute data.
    Uses the ForexiteConnection class.
    """
    mgc = MongoDatabaseConnection(database=db)
    fc = ForexiteConnection()
    if sleep: import time
    while start <= end:
        data = fc.get_data(start, start)
        for ticker in data:
            mgc.set_data(data[ticker], [ticker], volume=False, adj_close=False)
        start += datetime.timedelta(1)
        if sleep: time.sleep(sleep)

def populate_oanda_currency(account_id, access_token, symbols, granularity='M5', periods=5000, db='symbol-data-5min-currency'):
    """
    Helper function to populate a local mongo db with currency minute data.
    Uses the OandaConnection class.
    """
    mgc = MongoDatabaseConnection(database=db)
    oc = OandaConnection(account_id, access_token)
    for symbol in symbols:
        data = oc.get_data(symbol, granularity=granularity, periods=periods)
        mgc.set_data(data, [symbol], adj_close=False)

def convert_1min_to_5min(db_name_1min, db_name_5min, symbols, start, end, volume=False):
    """
    Helper function to convert 1min data to 5min data.
    Specify the 1min database you want to convert, the 5min database to be created, the list of symbols,
    the start and end datetimes, and whether or not to include volume in the resampling.
    """
    import dataset
    mgc_old = MongoDatabaseConnection(database=db_name_1min)
    mgc_new = MongoDatabaseConnection(database=db_name_5min)
    d = dataset.Dataset(symbols, mgc_old, start, end)
    d.load_data()
    d.resample('5Min', volume=volume)
    mgc_new.set_data(d.data_frame, symbols, volume=volume, adj_close=False)

def convert_5min_to_15min(db_name_5min, db_name_15min, symbols, start, end, volume=False):
    """
    Helper function to convert 1min data to 5min data.
    Specify the 5min database you want to convert, the 15min database to be created, the list of symbols,
    the start and end datetimes, and whether or not to include volume in the resampling.
    """
    import dataset
    mgc_old = MongoDatabaseConnection(database=db_name_5min)
    mgc_new = MongoDatabaseConnection(database=db_name_15min)
    d = dataset.Dataset(symbols, mgc_old, start, end)
    d.load_data()
    d.resample('15Min', volume=volume)
    mgc_new.set_data(d.data_frame, symbols, volume=volume, adj_close=False)