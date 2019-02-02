# coding=utf-8
# -- IMPORTS --
from __future__ import unicode_literals
import hashlib
import time
import datetime
import base64
from flask import Flask, request, jsonify, redirect, url_for, render_template
from flaskext.mysql import MySQL
from flask_influxdb import InfluxDB

# -- INIT APP --

app = Flask(__name__)

# -- INIT MySQL & InfluxDB --

mysql = MySQL()
influx_db = InfluxDB(app=app)

# -- APP CONFIG --

app.config['MYSQL_DATABASE_USER'] = 'root'
app.config['MYSQL_DATABASE_PASSWORD'] = 'Makaveli'
app.config['MYSQL_DATABASE_DB'] = 'pli_users'
app.config['MYSQL_DATABASE_HOST'] = '127.0.0.1'
mysql.init_app(app)

# -- MYSQL OBJECTS --

conn = mysql.connect() #connect to MySQL
cursor = conn.cursor() #query builder

# Get all streets
def getStreets():

    dbcon = influx_db.connection #connect to InfluxDB
    dbcon.switch_database(database='pli')

    streets = []

    street_tags = dbcon.query("SELECT DISTINCT(street) from devices") #retrieving all unique street names from measurement
    tag_points = list(street_tags.get_points())

    for point in tag_points:

        streets.append(point['distinct']) #storing values in array

    return(streets)

# Get device street from its ID
def getStreetFromDeviceId(device_id):

    dbcon = influx_db.connection
    dbcon.switch_database(database='pli')

    street = dbcon.query("SELECT street from devices WHERE device = {0}".format(device_id))
    street = list(street.get_points(measurement='devices'))
    street = street[0]['street'] #retrieving value from list

    return(street)

# Removing unwanted characters from street names
def cleanStreetNames(streets):

    cleanStreets = []

    for street in streets:

        street = street.replace('_', ' ') #we want spaces in between words
        cleanStreets.append(street)

    return cleanStreets

# Increment device ID
def idIncrement():

    dbcon = influx_db.connection
    dbcon.switch_database(database='pli')

    tabledata = dbcon.query('SELECT MAX(device) FROM devices') #getting current max ID
    max_device = list(tabledata.get_points(measurement='devices'))

    if (max_device != []): #if there is at least one device
        id = max_device[0]['max'] #we retrieve the max ID
    else:
        id = 0 #else we set id at 0

    id = id + 1 #incrementing

    return(id)

# Decoding base 64 payload into valid light reading
def getLightReadingFromPayload(payload):

    payload= base64.b64decode(payload) #decoding base 64
    hex_light = payload[-2:] #light reading is last two digits, slicing string
    dec_light = int(hex_light, 16) #light reading is in hexadecimal format, converting to decimal
    float_light = float(dec_light) #influxDB value is a float, casting

    return(float_light)

# Retriving all devices as list
def getDevices():

    dbcon = influx_db.connection
    dbcon.switch_database(database='pli')

    tabledata = dbcon.query('SELECT * FROM devices')
    all_devices = list(tabledata.get_points(measurement='devices')) #we'll keep the lsit as is, so we can access attributes as needed

    return(all_devices)

# Is at least one device off?
def IsOneOff():

    all_devices = getDevices()
    NoOnesOff = []

    for device in all_devices:

        if (device['status'] == 0): #if device is off,
            return(device) #we stop the loop and return device

    return(NoOnesOff) #no device is off

# Retrieving data for time series chart
def highChartTimeSeries():

    dbcon = influx_db.connection
    dbcon.switch_database(database='pli')

    start_time = 1547856000000000000 #01/01/2019 (arbitrary)

    streets = getStreets()

    set = []
    data = []

    for street in streets:

        events_array = []
        set = []

        events = dbcon.query("select count(lumens) from events where street = '{0}' and time > {1} group by time(15m)".format(street, start_time))
        event_points = list(events.get_points())

        for event in event_points: #for each event

            event_array = []
            timestamp = int(time.mktime(datetime.datetime.strptime(event['time'], "%Y-%m-%dT%H:%M:%SZ").timetuple()) * 1000)
            event_array.append(timestamp) #we store event timestamp into array (in nanoseconds)
            event_array.append(event['count']) #we get the count for this 15-min span
            events_array.append(event_array) #we store this event's data into our main event array

        set.append(street) #final data is an array of arrays with street name...
        set.append(events_array) #...and corresponding events (count, timestamps)
        data.append(set)

    return(data)

# Retrieving data for weekly data chart
def chartJsWeekCount(week):

    dbcon = influx_db.connection
    dbcon.switch_database(database='pli')

    streets = getStreets()
    perStreetWeeklyCount = [] #we want to return an array of arrays with street name, count for the week, and color in each array
    i = 0 #dataset counter
    colors = ['#BBE2E9', '#B5F299'] #dataset colors

    from_week_day = datetime.datetime.strptime(week + '-1', "%Y-W%W-%w") - datetime.timedelta(days=7) #getting first day of the selected week
    monday_date = str(from_week_day.date()) #converting to date

    week_start_timestamp = int(time.mktime(datetime.datetime.strptime(monday_date, "%Y-%m-%d").timetuple())) * 1000000000 #beginning of time bracket
    week_end_timestamp = week_start_timestamp + 604800000000000 #end of time bracket

    for street in streets:

        weekly_events = dbcon.query("select count(lumens) from events where street = '{0}' and time >= {1} AND time <= {2} group by time(1d)".format(street, week_start_timestamp, week_end_timestamp)) #counting events per week in given timespan
        weekly_event_points = list(weekly_events.get_points())
        weekly_event_points = weekly_event_points[1:] #truncating list to account for influxdb's group by day (starts with previous day...)

        counts = []

        for event in weekly_event_points:
            counts.append(event["count"]) #isolating count

        color = colors[i] #getting dataset color
        i = i + 1

        if (i == 2): #we only have two colors, so...
            i = 0 #...guess we'll have to loop again

        perStreetWeeklyCount.append([street, counts, color]) #this is our final array

    monday_date = datetime.datetime.strptime(monday_date, '%Y-%m-%d').strftime('%d/%m/%Y') #now that we've used it, converting to user-friendly format

    return(perStreetWeeklyCount, monday_date)

# -- ROUTES -- #

#ALL USERS
@app.route('/getUsers', methods=['GET'])

def home():

    all_users = []
    cursor.execute("SELECT * FROM users")
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]

    for row in rows:

    	row = dict(zip(columns,row))
    	all_users.append(row)

    return jsonify({'users': all_users}),200

#LOGIN (get token)
@app.route('/signIn', methods=['GET', 'POST'])

def signIn():
    if (request.method == 'POST'):
        user = []
        login = request.form['login']
        sha_1 = hashlib.sha1(request.form['password'])
        password = sha_1.hexdigest()
        isSignedIn = cursor.execute("SELECT * FROM users WHERE login = (%s) AND password = (%s)", (login, password))
        if (isSignedIn):
            return redirect('/getEvents')
        else:
            error = "Identifiant ou mot de passe incorrect !"
            return render_template('login.html', error=error),401
    return render_template('login.html'),200

#SAVE USER WARNING/ALERT THRESHOLDS
@app.route('/admin', methods=['GET', 'POST'])

def create_settings():

    settings = []

    cursor.execute("SELECT * FROM alerts") #getting current values
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]

    for row in rows:

        row = dict(zip(columns,row))
        settings.append(row)

    warning_delay = settings[0]['warning_threshold'] #current value, to display on page load
    alert_delay = settings[0]['alert_threshold'] #current value, to display on page load

    if (request.method == 'POST'): #if user has made change (or not)

        warning_delay = request.form.get('warning')
        alert_delay = request.form.get('alert')
        error = ''

        if (alert_delay > warning_delay): #already made sure it's the case with js, double-checking
            cursor.execute("UPDATE alerts SET warning_threshold = (%s), alert_threshold = (%s);", (warning_delay, alert_delay)) #updating settings
        else:
            error = "Le seuil de déclenchement d'alerte doit être supérieur au seuil de déclenchement du monitoring !"
            return render_template('admin.html', error=error),400

    return render_template('admin.html', warning=warning_delay, alert=alert_delay),200

#CREATE NEW DEVICE
@app.route('/newDevice', methods=['GET', 'POST'])

def create_device():

    dbcon = influx_db.connection
    dbcon.switch_database(database='pli')

    allDevices = getDevices() #we want to show current device locations on map
    streets = getStreets() #so user can pick among existing
    cleanStreets = cleanStreetNames(streets) #cleaning

    if (request.method == 'POST'):

        status = int(request.form.get('status'))
        lat = request.form.get('lat')
        long = request.form.get('long')
        street = request.form.get('street')
        street = street.replace(' ', '_') #making street name one word
        id = idIncrement() #incrementing index

        json_body = [
            {
                "measurement": "devices",
                "tags": {
                    "latitude": lat,
                    "longitude": long
                },
                "fields": {
                    "status": status,
                    "device": id,
                    "street": street
                }
            }
        ]
        dbcon.write_points(json_body) #and we insert

    return render_template('newDevice.html', devices=allDevices, streets=cleanStreets),200

#MAP PAGE (HOME)
@app.route('/map', methods=['GET', 'POST'])

def map():

    allDevices = getDevices()
    OffDevices = IsOneOff() #se we can display it/them red and center map on it/them

    return render_template('home.html', OffDevices=OffDevices, devices=allDevices),200

#DATA PAGE
@app.route('/getEvents', methods=['GET', 'POST'])

def getEvents():

    dbcon = influx_db.connection
    dbcon.switch_database(database='pli')

    streets = getStreets()
    week = '2019-W03' #default (so chart is not empty on GET page load)
    post = False

    if (request.method == 'POST'):
        week = request.form['week']
        post = True #we'll load page tabs differently if this is a weekly chart request

    timeSeriesData = highChartTimeSeries() #data for time series graph
    weeklyData = chartJsWeekCount(week)[0] #data for week graph
    monday_date = chartJsWeekCount(week)[1] #for week chart title

    return render_template('allEvents.html', post=post, week=week, streets=streets, week_monday_date=monday_date, perStreetWeeklyCount=weeklyData, timeSeriesData=timeSeriesData),200

#POST ONE EVENT
@app.route('/postEvent', methods=['POST'])

def postEvent():

    dbcon = influx_db.connection
    dbcon.switch_database(database='pli')

    content = request.json #getting request json body

    device_id = content['hardware_serial']
    street = getStreetFromDeviceId(device_id) #we want to store device street as event tag

    payload = content['payload_raw']
    float_light = getLightReadingFromPayload(payload) #extracting database-worthy light reading from payload

    time = content['metadata']['time'] #time the TTN server received frame

    json_body = [
        {
            "measurement": "events",
            "tags": {
                "device": device_id,
                "street": street
            },
            "fields": {
                "lumens": float_light
            },
            "time": time
        }
    ]

    dbcon.write_points(json_body) #and we insert

    return jsonify({'code':201,'message': 'Created'}),201

#404 ROUTE
@app.errorhandler(404)

def not_found(error):
	return jsonify({'code':404,'message': 'Not Found'}),404

#RUNNING APP
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8000)
