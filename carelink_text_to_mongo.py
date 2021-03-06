'''
Copyright (c) 2016 Michael Stebbins
Based on code from KainokiKaede (https://gist.github.com/KainokiKaede/7251872)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

USAGE
 1. Run Carelink with the BG meter to upload data, then export CSV including 
     date desired.
 2. Use carelink_xls_to_text.py to generate text file of all pertinent 
     medtronic output from carelink .csv file.
 3. Set INPUT_FILENAME below to the name of the csv file generated.
 4. Run script. All pertinent lines from csv file will be entered as separate 
     events into Mongolab database.
 5. Run reports in Nightscout to see your Medtronic data on your day-to-day plots
 6. Keep fighting the good fight, and kicking diabetes' %$$!
'''

# IMPORTS
#---------------------------------------------------------------------------------------------------
from pymongo import MongoClient
import time
import datetime


# USER INPUTS
#---------------------------------------------------------------------------------------------------
DUPLICATE_THRESHOLD_IN_SECONDS = 10
INPUT_FILENAME = 'testoutput.txt'
USE_CONFIG_FILE_FOR_LOGIN = False

MONGO_URL = 'mongodb://DataIn:g8cr3Xyvg9h8@ds054298.mongolab.com:54298/mikestebbinsdb2'
DB_NAME = 'mikestebbinsdb2'

global counter
counter = 0


# FUNCTIONS
#---------------------------------------------------------------------------------------------------
def enteredBy_incrementer():
    global counter
    counter = counter + 1
    result = "computer"+str(counter)
    return result


def convert_time_to_utc(input_string):
    # remove the utc offset string from the main string
    create_time_base = input_string[0:19]
    time_utc = datetime.datetime.strptime(create_time_base,'%Y-%m-%d %H:%M:%S')
    # change the utc datetime to the appropriate string
    datetime_str = datetime.datetime.strftime(time_utc,'%Y-%m-%dT%H:%M:%S.000Z')
    return datetime_str


def process_bolusnormal(input_line):
    datetime_str = convert_time_to_utc(input_line[1])
    bolus = input_line[2]
    post = {
            "eventType":"Meal Bolus",
            "enteredBy":enteredBy_incrementer(),
            "insulin": bolus,
            "units": "mg/dL",
            "created_at":datetime_str
            }    
    return post


def process_boluswizardbolusestimate(input_line):
    datetime_str = convert_time_to_utc(input_line[1])
    bg    = int(input_line[2])
    carbs = input_line[3]
    bolus = input_line[4]
    
    temp_dict = {}

    if carbs is not '0':
        temp_dict["carbs"] = carbs

    if bg is not 0:
        temp_dict["glucose"] = bg
        temp_dict["glucoseType"] = "Finger"

    if bolus is not '0':
        temp_dict["insulin"] = bolus
        temp_dict["units"] = "mg/dl"
  
    temp_dict["eventType"] = "Meal Bolus"
    temp_dict["enteredBy"] = enteredBy_incrementer()
    temp_dict["created_at"] = datetime_str

    post = temp_dict
    return post


def process_rewind(input_line):
    datetime_str = convert_time_to_utc(input_line[1])
    post = {
            "eventType":"Site Change",
            "enteredBy":enteredBy_incrementer(),
            "created_at":datetime_str
            }    
    return post


def process_bgcapturedonpump(input_line):
    datetime_str = convert_time_to_utc(input_line[1])
    bg = int(input_line[2])
   
    post = {
            "eventType": "BG Check",
            "enteredBy":enteredBy_incrementer(),
            "glucose": bg,
            "glucoseType": "Finger",
            "units": "mg/dL",
            "created_at":datetime_str
            }    
    return post


def process_changetempbasalpercent(input_line):
    datetime_str = convert_time_to_utc(input_line[1])
    temp_basal_percent = int(input_line[2])
    temp_basal_duration = int(input_line[3])
    
    # pump reports absolute percent, nightscout wants delta percent
    # i.e., 150(%) temp basal on pump is entered as 50(%) in nightscout
    temp_basal_percent = temp_basal_percent - 100
    if temp_basal_percent < -100:
        print ('temp basal rate is impossible, must be wrong')
    else:
        post = {
                "eventType": "Temp Basal",
                "enteredBy":enteredBy_incrementer(),
                "duration": temp_basal_duration,
                "percent": temp_basal_percent,
                "created_at":datetime_str
                }    
        return post


def obtain_mongo_login_info():
    # MONGOLAB DATABASE LOG-IN INFO PULLED FROM CONFIG FILE (CREATE YOUR OWN LIKE IN EXAMPLE)
    with open('.config') as f:
        config = f.read().splitlines()
    MONGO_URL = config[0]
    DB_NAME = config[1]
    return[MONGO_URL,DB_NAME]


def connect_to_mongo(MONGO_URL,DB_NAME):
    try:
        DBclient = MongoClient(MONGO_URL)
        DB = DBclient[DB_NAME]
        COLLECTION_TREATMENTS = DB['treatments']
        print("connected to MongoDB")
        return [DBclient,COLLECTION_TREATMENTS]
    except:
        print ('can not connect to DB make sure MongoDB is running')
    

def count_mongo_entries():
    try:
        number_of_entries = COLLECTION_TREATMENTS.count()
        print ('number of posts already existing = ',number_of_entries) 
    except Exception:
        print ('error: could not count posts for some reason or another')
        number_of_entries = 0
        print() 


def read_lines_from_file():
    file = open(INPUT_FILENAME, 'r')
    master_list = []
    counter = 0
    for line in file:
        if '***' in line:
            print('skipping header line')
        else:
            master_list.append(line)
            counter = counter + 1
    return [counter,master_list]
    

def parse_lists(input_list_of_lists):
    master_list_of_lists = []    
    for line in input_list_of_lists:
        master_list_of_lists.append(line.split(","))
    return master_list_of_lists
    
    
def remove_duplicate_lists(parsed_lists):
    print('length of input list of lists =',len(parsed_lists))  
    revised_list_of_posts = []    
    for i in range (0, len(parsed_lists)):
        if i == 0:
            revised_list_of_posts.append(parsed_lists[i])
        else:
            if parsed_lists[i] == parsed_lists[i-1]:
                pass
            else:
                revised_list_of_posts.append(parsed_lists[i])
    print('length of output list of posts =', len(revised_list_of_posts)) 
    return revised_list_of_posts 
    

def insert_datetime_field(input_list_of_lists):
    master_list_of_lists = []
    for line in input_list_of_lists:
        timestamp = datetime.datetime.strptime(line[2],'%Y-%m-%d %H:%M:%S+00:00')        
        line.insert(0,timestamp)        
        master_list_of_lists.append(line)
    return master_list_of_lists


def merge_duplicate_events(sorted_lists):
    print('length of sorted_lists =',len(sorted_lists)) 
    skip_next = False   
    
    sorted_lists.append([[],[],[]])  # so iterator doesn't go out of index range
    list_of_posts = []    

    for i in range (0,len(sorted_lists)-1):      
        if skip_next == True:
            skip_next = False
        else:
            print('i =',i)
            print()  
            curr = sorted_lists[i]
            next = sorted_lists[i+1]
            labelA = 'BolusNormal'
            labelB = 'BolusWizardBolusEstimate'

            if i < len(sorted_lists)-2:         
                time_delta_seconds = (next[0] - curr[0]).total_seconds()
            else:
                time_delta_seconds = 999
            if time_delta_seconds < DUPLICATE_THRESHOLD_IN_SECONDS:
                print(time_delta_seconds)
                print(curr), print()
                print(next), print()
                if curr[2] == labelB and next[2] == labelA:
                    post = meld_two_bolus_lines(curr,next)
                    print(post)
                    skip_next = True
                if curr[2] == labelA and next[2] == labelB:
                    post = meld_two_bolus_lines(next,curr)
                    print(post)
                    skip_next = True  
            else:
                post = curr[1]
                i = i + 1
            list_of_posts.append(post)
    sorted_lists = sorted_lists[0:-1]
    return list_of_posts


def meld_two_bolus_lines(BolusWizardEstimate,BolusNormal):         
    new_insulin = BolusNormal[1]['insulin']
    BolusWizardEstimate[1]['insulin'] = new_insulin
    post = BolusWizardEstimate[1]
    return(post)
            

def decode_parsed_lists(parsed_lists):
    master_list = []    
    for line in parsed_lists:
        if 'BolusNormal' in line:
            post = process_bolusnormal(line)
        if 'BolusWizardBolusEstimate' in line:
            post = process_boluswizardbolusestimate(line)
        if 'Rewind' in line:
            post = process_rewind(line)
        if 'BGCapturedOnPump' in line:
            post = process_bgcapturedonpump(line)
        if 'ChangeTempBasalPercent' in line:
            post = process_changetempbasalpercent(line)
        line.insert(0,post)
        master_list.append(line)
    return master_list
    
    
def remove_duplicate_posts(list_of_posts):
    print('length of input list of posts =', len(list_of_posts))    
    revised_list_of_posts = []    
    for i in range (0, len(list_of_posts)):
        if i == 0:
            revised_list_of_posts.append(list_of_posts[i])
        else:
            if list_of_posts[i] == list_of_posts[i-1]:
                pass
            else:
                revised_list_of_posts.append(list_of_posts[i])
    print('length of output list of posts =', len(revised_list_of_posts)) 
    return revised_list_of_posts         
            

def post_the_posts(COLLECTION_TREATMENTS,list_of_posts):
    for post in list_of_posts:
        try:  
            post_id = COLLECTION_TREATMENTS.insert_one(post)
            print (post_id) 
        except:
            print (post)
        time.sleep(0.1)


#-----------------------------------------------------------------------------
# MAIN FUNCTION
#-----------------------------------------------------------------------------
print('----------------------------------------------------------------------')

time_then = time.time()

if USE_CONFIG_FILE_FOR_LOGIN == True:
    MONGO_URL,DB_NAME = obtain_mongo_login_info()

DBclient,COLLECTION_TREATMENTS = connect_to_mongo(MONGO_URL,DB_NAME)

count_mongo_entries()

counter,master_list = read_lines_from_file()
print('total lines in file =',counter)

parsed_lists = parse_lists(master_list)

parsed_lists = remove_duplicate_lists(parsed_lists)

decoded_lists = decode_parsed_lists(parsed_lists)
#now, each entry is [{post dictionary},parsed list from text]

datetime_sortable_lists = insert_datetime_field(parsed_lists)
#now, each entry is [datetime object,{post dict},parsed list from text]

sorted_lists = sorted(datetime_sortable_lists, key=lambda x: x[0])

list_of_posts = merge_duplicate_events(sorted_lists)

list_of_posts = remove_duplicate_posts(list_of_posts)

post_the_posts(COLLECTION_TREATMENTS,list_of_posts)
         
DBclient.close()