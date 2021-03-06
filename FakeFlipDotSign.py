"""
Since this is basically firmware, it should be able to handle a lot of hard coding.  Some of the elements,
especially the events to add, will be difficult to allow the user to send.

1.  ???
2.  List of message objects
3.  Pop random element off list of message objects
4.  When list reaches X entries, start the ??? process in a new thread to update the list of message objects
5.  Repeat with new list of message objects
"""


from MessageClasses import *
from DisplayClasses import *
import googleapiclient.errors
import copy
import random
import time
import serial
from TransitionFunctions import *
from Generate_Layout import *
from MessageGenerator import *
from WeatherClasses import *

fontsize = 9
minfontsize = 3

base_directory = os.path.dirname(__file__)
weather_API_key = open(os.path.join(base_directory,'WeatherKey.txt')).readline()
default_font_path = os.path.join(base_directory,'PressStart2P.ttf')
google_sheet_id = open(os.path.join(base_directory,'GoogleSheet.txt')).readline()
google_location_key = open(os.path.join(base_directory,'Google_Location_Key.txt')).readline()
home_location = input('Please enter zio code for home location: ')

z = SimpleTransition('','z')
def GetGoogleSheetData(sheetID, credentials, lstCalendars, lstTemporaryMessages):
    # Create google sheets object
    http = credentials.authorize(httplib2.Http())
    discoveryurl = ('https://sheets.googleapis.com/$discovery/rest?'
                    'version=v4')
    result = {}
    try:
        SHEETS = discovery.build('sheets', 'v4', http=http, discoveryServiceUrl=discoveryurl)
    except httplib2.ServerNotFoundError:
        raise IOError("No Internet Connection")
    try_again = True
    num_times = 1
    # Service may be unavailable, so try at least 3 times, backing off during
    while try_again:
        try:
            # if successful, then update TryAgain to get out of the loop
            result = SHEETS.spreadsheets().values().get(spreadsheetId=sheetID, range="Messages!A:C").execute()
            try_again = False
        except googleapiclient.errors.HttpError:
            num_times += 1
            if num_times == 4:
                # if we've done this 4 times, raise an ValueError to be caught by the calling function
                raise ValueError
            # wait before trying again
            time.sleep(int(random.random() * (2 ^ num_times - 1)))
        except httplib2.ServerNotFoundError:
            raise IOError("No Internet Connection")

    for processmessage in result['values']:
        if processmessage[0] == "GCal":
            lstCalendars.append(GoogleCalendar(processmessage[1], credentials))
        elif processmessage[0] == "SpecificDateMessage":
            lstTemporaryMessages.append(SpecificDateMessage(processmessage[1], parse(processmessage[2])))
        elif processmessage[0] == "BasicTextMessage":
            lstTemporaryMessages.append(BasicTextMessage(processmessage[1]))
        elif processmessage[0] == "MessageGenerator":
            lstGeneratedMessages = Message_Generator(processmessage[1],processmessage[2]).create_messages()
            for Generated_Message in lstGeneratedMessages:
                lstTemporaryMessages.append(Generated_Message)
        elif processmessage[0] == "WeatherLocation":
            location = WeatherLocation(processmessage[1], processmessage[2], weather_API_key, default_font_path)
            forecast = location.ten_day_forecast(rows=21, columns=168, daysfromnow=0)
            if forecast is not None:
                lstTemporaryMessages.append(forecast)

z = serial.Serial('/dev/cu.usbmodemFD131',9600)

Display = FakeFlipDotDisplay(columns=168,rows=21, serialinterface=z, layout=Generate_Layout_2())

# set up list of transit messages - since this is static, it is done outside the loop
lstTransitMessages = []


#while True: - only run through the process once since the fake sign is mostly for testing
# Reset list of calendars and messages to display
lstCalendars = []
lstMessagestoDisplay = []
lstTemporaryMessages = []
try:
    # attempt to get new temporary messages and calendars from the google spreadsheet
    # the "check" list is used so that the temporary messages list is only replaced if the internet is up
    check = []
    GetGoogleSheetData(google_sheet_id, get_credentials(), lstCalendars, check)
    lstTemporaryMessages = check
    print("Pulled google sheet data")
except ValueError:
    # if the internet is down, do nothing
    print("Found no internet connection when pulling google sheet data.")
    pass
# except ValueError:
#     print("No google service when opening google sheet.")
#     lstTemporaryMessages.append(BasicTextMessage("No Google Service"))

# for each calendar in the list of google calendars we want to display
# if the internet connection check earlier was unsuccessful, then this will be an empty list and the whole block
# will be skipped
for cal in lstCalendars:
    # create a temporary list of messages from the google calendar routine
    temp = []
    try:
        # run the message creation
        in_tuple = cal.create_messages(5)
        # the first element of the tuple is a list of event messages
        temp = in_tuple[0]
        # the second element of the tuple is a list of tuples
        # first element of each tuple is the location string
        # second element is the number of days until that event
        for location in in_tuple[1]:
            # turn the first element of each tuple into a weather location
            weather_location = WeatherLocation(location[0], location[0], weather_API_key,
                                               default_font_path, google_location_key=google_location_key,
                                               home_location=home_location)
            # get the forecast - go ahead a max of five days or until the event starts
            num_of_days_until = min(5, location[1])
            weather_forecast = weather_location.ten_day_forecast(rows=21, columns=168, daysfromnow=num_of_days_until)
            temp.append(weather_forecast)
        print("Created messages from google calendar.")
    except IOError:
        pass
        print("No internet connection when pulling from google calendar.")
    # for each message we got back from GCal, add that to the list of temporary messages
    for message in temp:
        lstTemporaryMessages.append(message)
# if it's between 6 and 9 AM, we care a lot more about transit than anything else, add a lot more of those
if 6 < datetime.datetime.now().hour < 9:
    for i in range(3):
        lstMessagestoDisplay += copy.deepcopy(lstTransitMessages)
# build the list of messages to display
lstMessagestoDisplay += copy.deepcopy(lstTransitMessages)
lstMessagestoDisplay += lstTemporaryMessages
random.shuffle(lstMessagestoDisplay)

# for each messages in our list to display, make the display show it then wait for 1 second before sending next
for message in lstMessagestoDisplay:
    try:
        Display.update(SimpleTransition, message,
                       font=ImageFont.truetype('/Users/cmcd/PycharmProjects/Sign/PressStart2P.ttf', size=fontsize))
    # if we've got an internet connection problem, tell the user about it
    except IOError:
        Display.update(SimpleTransition, BasicTextMessage("Check Internet"),
                       font=ImageFont.truetype('/Users/cmcd/PycharmProjects/Sign/PressStart2P.ttf', size=fontsize))
    except ValueError:
        # if it's a one time specific date message, then valueerror means the date is passed
        # if it's not a one-time specific date message, then this is a real error
        if isinstance(message, OneTimeSpecificDateMessage):
            print("Had a case where a one-time specific date message was in the past.")
            pass
        elif isinstance(message, BasicTextMessage):
            trysize = fontsize
            while trysize >= minfontsize:
                try:
                    print("Tried font size: " + str(trysize))
                    Display.update(SimpleTransition, message,
                   font=ImageFont.truetype('/Users/cmcd/PycharmProjects/Sign/PressStart2P.ttf', size=trysize))
                    break
                except ValueError:
                    trysize += -1
        else:
            raise ValueError

