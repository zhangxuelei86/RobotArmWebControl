#!/usr/bin/env python
#from threading import Lock
#
#
#from flask_socketio import SocketIO, emit, join_room, leave_room, close_room, rooms, disconnect
import os

ABS_PATH = os.path.dirname(
    os.path.abspath(__file__))  # DIRECTORY OF PYTHON APP
print(ABS_PATH)

import json

import smbus2
import threading
from datetime import datetime

import logging
import signal
import sys
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont


import sys
import time
from flask import Flask, render_template, session, request, redirect, jsonify
import socket
import fcntl
import struct
import os
from pathlib import Path
from netifaces import interfaces, ifaddresses, AF_INET
from os import walk

abspath = os.path.dirname(os.path.abspath(__file__))


# SETUP I2C BUS
bus = smbus2.SMBus(1)
DEVICE_ADDRESS = 8  # ADRESS OF THE ARDUINO DUE I2C SLAVE

# LOAD IP ADRESSES FROM ALL INTERFACVES ON THE SYSTEM
ips = {}


def load_ip_adresses_from_interface():
    for ifaceName in interfaces():
        addresses = [
            i['addr'] for i in ifaddresses(ifaceName).setdefault(
                AF_INET, [{
                    'addr': 'No IP addr'
                }])
        ]
        ips[ifaceName] = ''.join(addresses)
load_ip_adresses_from_interface()
print(ips)

# LOAD FONT IN DIFFERENT SIZES
font = ImageFont.load_default()
font_healine = ImageFont.truetype(abspath + '/Retron2000.ttf', 16)
font_small = ImageFont.truetype(abspath + '/Retron2000.ttf', 12)

# SETUP FOR FLASK WEBSERVER
async_mode = None
app = Flask(__name__, static_url_path='/assets', static_folder='assets')
app.config['SECRET_KEY'] = 'secret!'

# SETUP FOR ROBOT ARM PROGRAMS
programs_names = []
programm_running = False
programm_data = []
programm_index = 0
programm_lines = []  # RAW PRG LINES


program_registers = {
    "A":0,
    "B":0,
    "C":0,
    "D":0
}
program_registers_init = program_registers


loaded_programs = []


def load_clibration_json(_file):
    jd = {
        "AXIS_1_TOTAL_DGREE": 350,
        "AXIS_2_TOTAL_DGREE": 170,
        "AXIS_3_TOTAL_DGREE": 170,
        "AXIS_4_TOTAL_DGREE": 170,
        "AXIS_5_TOTAL_DGREE": 350,
        "AXIS_1_MIN": 0,
        "AXIS_1_MAX": 255,
        "AXIS_2_MIN": 0,
        "AXIS_2_MAX": 255,
        "AXIS_3_MIN": 0,
        "AXIS_3_MAX": 255,
        "AXIS_4_MIN": 0,
        "AXIS_4_MAX": 255,
        "AXIS_5_MIN": 0,
        "AXIS_5_MAX": 255,
    }
    try:
        with open(_file) as json_file:
            data = json.load(json_file)
            #TODO CLEAN
            jd = data
    except:
        print("--- load " + _file + " failed using default")

    return jd

print("---------------")
robot_calibration_data = load_clibration_json(ABS_PATH + "/../arduino_controller/calibration.json")
print(robot_calibration_data)
print("---------------")


#print(int(robot_calibration_data["AXIS_1_MAX"]))





def math_map(val, src, dst):
    """
    Scale the given value from the scale of src to the scale of dst.
    """
    return ((val - src[0]) / (src[1] - src[0])) * (dst[1] - dst[0]) + dst[0]


def map_pot_to_degree(_axis_id, val):
    key_prefix = ""

    if _axis_id == 0:
        key_prefix = "AXIS_1_"
    elif _axis_id == 1:
        key_prefix = "AXIS_2_"
    elif _axis_id == 2:
        key_prefix = "AXIS_3_"
    elif _axis_id == 3:
        key_prefix = "AXIS_4_"
    elif _axis_id == 4:
        key_prefix = "AXIS_5_"
    else:
        return -1

    return int(
        math_map(val, [
            int(robot_calibration_data[key_prefix + "MIN"]) * 1.0,
            int(robot_calibration_data[key_prefix + "MAX"]) * 1.0
        ], [0,
            int(robot_calibration_data[key_prefix + "TOTAL_DGREE"]) * 1.0]))


def map_degree_to_pot(_axis_id, val):
    key_prefix = ""

    if _axis_id == 0:
        key_prefix = "AXIS_1_"
    elif _axis_id == 1:
        key_prefix = "AXIS_2_"
    elif _axis_id == 2:
        key_prefix = "AXIS_3_"
    elif _axis_id == 3:
        key_prefix = "AXIS_4_"
    elif _axis_id == 4:
        key_prefix = "AXIS_5_"
    else:
        return -1

    return int(
        math_map(
            val,
            [0,
             int(robot_calibration_data[key_prefix + "TOTAL_DGREE"]) * 1.0], [
                 int(robot_calibration_data[key_prefix + "MIN"]) * 1.0,
                 int(robot_calibration_data[key_prefix + "MAX"]) * 1.0
             ]))


ROBOT_PROGRAM_DIR = "ROBOT_PROGRAMS"


# LOADS ALL .prg PROGRAMM FILES
def get_all_robot_programs_in_dir():
    global programs_names
    files = os.listdir(ABS_PATH + "/" + ROBOT_PROGRAM_DIR)
    print(ABS_PATH)
    programs_names = []
    print(files)
    for f in files:
        if f.endswith('.prg'):  # LOKK FOR FILES ENDS WITH .prg
            fn = f.replace('.prg', '')
            print(fn)
            programs_names.append(fn)
            print("---ADD PRG ---")


get_all_robot_programs_in_dir()
cursor_index = 0
print(programs_names)

btn_block = False
time_stamp = 0.0
update_disp = False






def thread_function(name):
    global programm_running
    global programm_data
    global programm_index
    #  global bus
    global update_disp
    thread_step_counter = 0

    global bus
    data = []
    while True:
        if programm_running:
            print('--- PRG RUNNING ---')

            pos = programm_data[programm_index]  #GET NEXT INSTRUCTION
            print(pos)

            
            try:
                data = bus.read_i2c_block_data(DEVICE_ADDRESS, 99,15)  #READ I2C BUS 10 INT VALUES
                print(data)
    #CONVERT TO DEGREE
                data[0] = map_pot_to_degree(0, data[0])
                data[1] = map_pot_to_degree(1, data[1])
                data[2] = map_pot_to_degree(2, data[2])
                data[3] = map_pot_to_degree(3, data[3])
                data[4] = map_pot_to_degree(4, data[4])
                #print(data)
        #update_display()
            except:
                print("--- RESTART BUS ---")
                bus = smbus2.SMBus(1)
        
            
            #print(abs(data[0]-map_degree_to_pot(0,int(pos.get('axis_0'))))

            if thread_step_counter > int(pos.get('delay')):
                print("------------- WRITE CMD ------------------------------------------")
                programm_index = programm_index + 1
                thread_step_counter = 0
                bus.write_i2c_block_data(DEVICE_ADDRESS, 0x00,[1, map_degree_to_pot(0,int(pos.get('axis_0')))])
                time.sleep(0.1)
                bus.write_i2c_block_data(DEVICE_ADDRESS, 0x00,[2, map_degree_to_pot(1,int(pos.get('axis_1')))])
                time.sleep(0.1)
                bus.write_i2c_block_data(DEVICE_ADDRESS, 0x00,[3, map_degree_to_pot(2,int(pos.get('axis_2')))])
                time.sleep(0.1)
                bus.write_i2c_block_data(DEVICE_ADDRESS, 0x00,[4, map_degree_to_pot(3,int(pos.get('axis_3')))])
                time.sleep(0.1)
                bus.write_i2c_block_data(DEVICE_ADDRESS, 0x00,[5, map_degree_to_pot(4,int(pos.get('axis_4')))])
                time.sleep(0.1)
                bus.write_i2c_block_data(DEVICE_ADDRESS, 0x01,[int(pos.get('gripper'))])
                time.sleep(0.1)

            if programm_index >= len(programm_data):  # CHECK PROGRAM FINISHED
                print("-- PRG FINISHED --")
                programm_running = False
                programm_index = 0
                thread_step_counter = 0
                time.sleep(1)
                #update_display()
            #TODO TIMER COUNTER FOR NEXT STEP
            #time.sleep(int(pos.get('delay')))
        time.sleep(1)
        thread_step_counter = thread_step_counter + 1


program_execution_thread = threading.Thread(target=thread_function, args=(1, ))
program_execution_thread.start()



# SEND AXIS LIMIT CONFIG
@app.route('/config')
def config():
    return jsonify(robot_calibration_data)

# STATIC WEBSERVER PATH FOR IMAGES AND SCRIPTS
@app.route('/assets/<path:path>')
def static_file(path):
    return app.send_static_file(path)


# API CALL /axisx TO SET AN AXIS
@app.route('/axis')
def axis():
    id = request.args.get('id') # 0-4
    dgr = request.args.get('degree')
    pot_val = map_degree_to_pot(int(id),int(dgr))

    #print(id,dgr, pot_val)
    try:
        bus.write_i2c_block_data(DEVICE_ADDRESS, 0x00,[int(id)+1, pot_val])
        return jsonify(status="ok")
    except :
        return jsonify(status="err")
    # WRITE TO I2C BUS; COMMAND 0 AND AXISX ID AND VALUE



# API CALL TO SET THE GRIPPER STATE
@app.route('/gripper')
def gripper():
    state = request.args.get('state')

    #print(state)
    ledout_values = [int(state), int(state)]  #send axis_id
    bus.write_i2c_block_data(
        DEVICE_ADDRESS, 0x01,
        ledout_values)  #WRITE TO I2C BUS; COMMAND 1 AND GRIPPER STATE
    return jsonify(status="ok")


# API CALL TO GET STATES FROM ALL AXIS
@app.route('/axis_state')
def get_axis_state():
    global bus
    data = []
    try:
        data = bus.read_i2c_block_data(DEVICE_ADDRESS, 99,15)  #READ I2C BUS 10 INT VALUES
        #print(data)
    #CONVERT TO DEGREE
        data[0] = map_pot_to_degree(0, data[0])
        data[1] = map_pot_to_degree(1, data[1])
        data[2] = map_pot_to_degree(2, data[2])
        data[3] = map_pot_to_degree(3, data[3])
        data[4] = map_pot_to_degree(4, data[4])
        #print(data)
        #update_display()
        return jsonify(status=data)
    except:
        print("--- RESTART BUS ---")
        bus = smbus2.SMBus(1)
        return jsonify(status=data)
    
    


# API CALL TO GET STATES FROM ALL AXIS
@app.route('/axis_state_raw')
def axis_state_raw():
    global bus
    data = bus.read_i2c_block_data(DEVICE_ADDRESS, 99,
                                   15)  #READ I2C BUS 10 INT VALUES
    print(data)
    #CONVERT TO DEGREE
    #data[0] = map_pot_to_degree(1, data[0])
    #data[1] = map_pot_to_degree(2, data[1])
    #data[2] = map_pot_to_degree(3, data[2])
    #data[3] = map_pot_to_degree(4, data[3])
    #data[4] = map_pot_to_degree(5, data[4])
    #print(data)
    #update_display()
    return jsonify(status=data)



def load_prg(_dry_load = False):
    global programm_running
    global programm_data
    global programm_index
    pro_data = {}
    programm_running = False
    programm_data = []
    programm_index = 0
    #GENERATE PROGRAM FILEPATH DEPENDS ON SELECTED ITEM cursor_index
    name = programs_names[cursor_index] + ".prg"
    path = os.path.dirname(os.path.abspath(__file__)) + "/"+ROBOT_PROGRAM_DIR+"/" + name

    pro_data["name"] = name
    pro_data["file"] = path
    pro_data["index"] = cursor_index
    pro_data["autostart"] = False
    pro_data["conditions"] = []
    pro_data["marker"] = []

    line_counter = 0
    line_total = 0
    print("open " + path)
    #CHECK FILE EXISTS
    my_file = Path(path)
    if my_file.is_file():
        print("FILE READING")
    else:
        print("FILE NOT EXISTS")
    #READ FILE IN; IGNORE COMMENTS LINES; SPLIT AXISX VALUES AND APPEND IT TO THE PROGRAM DICTIONARY
    try:
        with open(path) as fp:
            line = fp.readline()
            while line:
                line = fp.readline()
                #print(line)
                if line.find("#") < 0:  # NO COMMENTS LINE FILTER
                    # check autostart
                    if line == "":
                        print("empty_line_skip")
                        continue

                    if "__AUTOSTART__" in line:
                        print("found __AUTOSTART__ in program")
                        pro_data["autostart"] = True
                        line_total = line_total + 1
                        continue

                    if "__MARKER_" in line:
                        print("found __MARKER_ in program")
                        sp = line.split("_")

                        if len(sp) == 6:
                            print(sp)
                            pro_data["marker"].append({
                                'type': 'marker',
                                'at_line': line_total,
                                'name': str(sp[3])
                            })
                            line_total = line_total+1
                        continue

                    if "__JUMP_" in line: #__JUMP_<marker_
                        sp = line.split("_")
                        if len(sp) == 6:
                            print("found __JUMP_ in program")
                            print(sp)

                            pro_data["conditions"].append({
                                'type':
                                'jump',
                                'at_line':
                                line_total,
                                'to_marker':
                                str(sp[3])
                            })
                            line_total = line_total+1
                        continue
                    #    #TODO

                    x = line.split()  #SPLIT FOR WHITESPACE
                    if len(x) == 7:  # LEN CHECK FOR STATEMENTS
                        #print(x)
                        programm_data.append({
                            'type': 'position',
                            'axis_0': x[0],
                            'axis_1': x[1],
                            'axis_2': x[2],
                            'axis_3': x[3],
                            'axis_4': x[4],
                            'gripper': x[5],
                            'delay': x[6],
                            'at_line': line_total,
                        })
                        line_counter =line_counter+1
                        line_total = line_total+1
                    else:
                        print("---prg parse len chek failed")
                        print(x)
                        #print(line)
            fp.close()
        print("-- PRG LOADED ---")
        print(programm_data)

        pro_data["programm_data"] = programm_data

        if len(programm_data) > 0:
            if _dry_load:
                programm_running = False
            else:
                programm_running = True
    except:
        pass
    return pro_data


def load_all_prgrams():
    global cursor_index
    cc = 0
    for n in programs_names:
        print("try to load programs :"+ n)
        cursor_index = cc

        prg_data_tmp = load_prg(True)
        loaded_programs.append(prg_data_tmp)


        #CHECK IF A PROGRAM IS MARKED AS AUTOSTART
        #if prg_data_tmp["autostart"]:
        #    cursor_index_a = cc
        #    programm_running = True
        #    programm_index = 0
        #    thread_step_counter = 0
        #    programm_data=prg_data_tmp["programm_data"]



        cc = cc +1

    #cursor_index = cursor_index_a


load_all_prgrams()
print(loaded_programs)
print("-----------------------------------------------------------")




#RELOADS ALL PROGRAMS FROM DISK
@app.route('/reload_programs')
def get_reload_programs():
    # STOP CURRENT PROGRAM
    global programm_running
    programm_running = False
    #LOAD .prg file list from disk
    global cursor_index
    global programs_names
    cursor_index = 0
    programs_names = []
    get_all_robot_programs_in_dir()
    #PARSE PROGRAMS
    global loaded_programs
    loaded_programs = []
    load_all_prgrams()
    return jsonify(loaded_programs=loaded_programs)


#GET A LIST OF PARSED PROGRAMS
@app.route('/get_programs')
def get_programs():
    global programs_names
    return jsonify(programs=programs_names)

@app.route('/get_programs_all')
def get_programs_all():
    global loaded_programs
    return jsonify(loaded_programs=loaded_programs)


@app.route('/save_program', methods=['POST'])
def save_program():
    data = request.form.to_dict(flat=False)
    print(data["name"][0])


    try:
        path = os.path.dirname(os.path.abspath(__file__)) + "/"+ROBOT_PROGRAM_DIR+"/" + data["name"][0]
        print(path)


        if data["content_raw"][0] == "":
            if os.path.exists(path):
                os.remove(path)
            else:
                print("The file does not exist")
            return jsonify({"state": "ok", "action":"deleted"})

        with open(path, "w") as text_file:
            text_file.write(data["content_raw"][0])
        return jsonify({"state":"ok", "action":"saved"})
    except IOError as e:
        print(e)
        return jsonify({"state":"err"})






#START A PROGRAM WITH THE GIVEN INDEX
@app.route('/start_program')
def start_program():
    global cursor_index
    id = request.args.get('id')

    cursor_index = int(id)
    load_prg()
    return jsonify(state=id) # TODO


#RETURN THE STATE OF A RUNNING PROGRAM
@app.route('/program_state')
def program_state():
    global programm_running
    global programm_data
    global programm_index
    global programs_names
    global cursor_index
    #id = request.args.get('id')
    return jsonify(
        programm_running=programm_running,
        programm_index=programm_index,
        len=len(programm_data),
        programm_data=programm_data)


@app.route('/stop_program')
def stop_program():
    global programm_running
    programm_running = False
    return jsonify(state=programm_running)  # TODO



# REDIRECT TO STATIC HTML FILE
@app.route('/index.html')
def index_html():
    return redirect('/assets/index.html')


# REDIRECT TO STATIC HTML FILE
@app.route('/')
def index_root():
    return redirect('/index.html')



# STARTUP
if __name__ == '__main__':






    # START WEBSERVER
    app.run()
    #socketio.run(app, host='0.0.0.0', debug=True)
