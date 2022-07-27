#!/usr/bin/python3
# -*- coding: utf-8 -*-

### written by Axel Schneider in July 2021 ###
### thanks to linuxmint-developers for XApp StatusIcon ###

import gi
gi.require_versions({"Gtk": "3.0", "Gst": "1.0", 'Gdk': '3.0', 'XApp': '1.0', 'Notify': '0.7'})
from gi.repository import Gtk, Gdk, Gst, XApp, Notify
from configparser import ConfigParser
from os import path
from sys import argv
import requests
import warnings
warnings.filterwarnings("ignore")

Gst.init(None)
Gst.init_check(None)


class MainWindow(XApp.StatusIcon):
    def __init__(self, parent=None):
        super(MainWindow, self).__init__()
        
        self.cwd = path.dirname(argv[0])
        self.volume = 0.6
        self.url = ""
        self.ch_name = ""
        self.is_playing = False
        self.appicon = path.join(self.cwd, "radio_bg.png")
        self.menu_icon = path.join(self.cwd, "menuicon.png")

        self.player = Gst.ElementFactory.make("playbin", "player")
        
        ### Listen for metadata
        self.old_tag = None
        self.bus = self.player.get_bus()
        self.bus.enable_sync_message_emission()
        self.bus.add_signal_watch()
        self.bus.connect('message::tag', self.on_tag)

        self.channel = 2
        
        self.slider = Gtk.Scale.new_with_range(0, 0, 99, 0.1)
        self.slider.set_value(self.volume * 100)
        self.slider.set_value_pos(3)
        self.slider.connect("value-changed", self.set_volume)
        v = float(self.slider.get_value()/100)
        self.player.set_property("volume", v)
        self.player.set_property("volume", v)

        self.channelsfile = path.join(path.dirname(argv[0]), "channels.txt")

        if path.exists(self.channelsfile) == True:
            with open(self.channelsfile, 'r') as f:
                self.chlist = f.read().splitlines()
            self.ch_names = []
            self.ch_urls = []
            for line in self.chlist:
                self.ch_names.append(line.partition(",")[0])
                self.ch_urls.append(line.partition(",")[2].lstrip().rstrip())
                
        self.create_menu()
                
        self.set_name("indicator")
        self.set_icon_name(self.appicon)
        self.set_primary_menu(self.action_channelsmenu)
        self.set_label("Radio")
        self.set_tooltip_text("use wheel to change volume\nmouse right click to toggle mute")
        self.connect("scroll-event", self.scroll_event)
        self.connect("activate", self.activate_event)
        
        self.notif = Notify.Notification() 
        Notify.init("Welcome to \nXAppTrayRadio")    

    def show_notification(self, message, *args):
        n = self.notif.new("XAppTrayRadio", message, self.appicon)
        n.set_timeout(3000)
        n.show()
        
        ### Handle song metadata
    def on_tag(self, bus, msg):
        taglist = msg.parse_tag()
        my_tag = f'{taglist.get_string(taglist.nth_tag_name(0)).value}'
        if my_tag:
            if not self.old_tag == my_tag and not my_tag == "None":
                print(my_tag)
                self.show_notification(my_tag)
                self.set_tooltip_text(my_tag)
                self.old_tag = my_tag
                
    def open_message_window(self, message, *args):
        dialog = Gtk.MessageDialog(
            flags=0,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=message)
        dialog.run()
        print("info dialog closed")

        dialog.destroy()
        
    def activate_event(self, icon, button, time):
        self.toggle_mute()
        
    def scroll_event(self, widget, amount, direction, time):
        v = self.player.get_property("volume")
        if(direction == 0):
            if v < 0.9:
                v = v + 0.01
        elif(direction == 1):
            if v > 0.1:
                v = v - 0.01
        self.slider.set_value(v * 100)

    def item_activated(self, wdg, i):
        print(f"playing {self.ch_names[i - 1]}\nURL: {self.ch_urls[i - 1]}")
        self.channel = i
        url = self.ch_urls[i - 1].rstrip()
        if url.endswith(".pls"):
            url = self.get_url_from_pls(url)
        if url.endswith(".m3u"):
            url = self.get_url_from_m3u(url)            
            
        self.play_radio(url)
        self.ch_name = self.ch_names[i - 1]
        self.set_label(self.ch_name)
        self.set_volume()
        self.is_playing = True

    def create_menu(self, *args):
        self.action_channelsmenu = Gtk.Menu()

        self.action_filequit = Gtk.ImageMenuItem(label="Exit", image=Gtk.Image.new_from_icon_name("application-exit", 2))
        self.action_filequit.connect("activate", self.handle_close)
        self.action_channelsmenu.append(self.action_filequit)

        sep_1 = Gtk.SeparatorMenuItem()
        self.action_channelsmenu.append(sep_1)
        
        img = Gtk.Image().new_from_icon_name("media-playback-start", Gtk.IconSize.BUTTON)
        self.action_start = Gtk.ImageMenuItem(label="Start playing", image=img)
        self.action_start.connect("activate", self.start_playing)
        self.action_channelsmenu.append(self.action_start)

        img = Gtk.Image().new_from_icon_name("media-playback-stop", Gtk.IconSize.BUTTON)
        self.action_stop = Gtk.ImageMenuItem(label="Stop playing", image=img)
        self.action_stop.connect("activate", self.stop_playing)
        self.action_channelsmenu.append(self.action_stop)

        sep_2 = Gtk.SeparatorMenuItem()
        self.action_channelsmenu.append(sep_2)
        
        img = Gtk.Image().new_from_icon_name("help-about", Gtk.IconSize.BUTTON)
        self.action_help = Gtk.ImageMenuItem(label="about XAppTrayRadio", image=img)
        self.action_help.connect("activate", self.show_help)
        self.action_channelsmenu.append(self.action_help)
        
        img = Gtk.Image().new_from_icon_name("accessories-text-editor", Gtk.IconSize.BUTTON)
        self.action_edit = Gtk.ImageMenuItem(label="edit channels", image=img)
        self.action_edit.connect("activate", self.edit_channels)
        self.action_channelsmenu.append(self.action_edit)

        sep_3 = Gtk.SeparatorMenuItem()
        self.action_channelsmenu.append(sep_3)

        img = Gtk.Image().new_from_icon_name("browser", Gtk.IconSize.BUTTON)
        self.action_clip = Gtk.ImageMenuItem(label="play URL from clipboard", image=img)
        self.action_clip.connect("activate", self.play_clipboard_url)
        self.action_channelsmenu.append(self.action_clip)

        sep_4 = Gtk.SeparatorMenuItem()
        self.action_channelsmenu.append(sep_4)

        # Radio List to menu
        for x in range(1, len(self.chlist) + 1):
            img = Gtk.Image.new_from_file(self.menu_icon)
            
            if self.ch_names[x - 1].startswith("--"):
                self.sub1 = Gtk.ImageMenuItem(label=self.ch_names[x - 1].replace("--", ""), image = img)
                self.action_channelsmenu.append(self.sub1)
                self.submenu1 = Gtk.Menu()
            else:
                action_channel = Gtk.ImageMenuItem(label=self.ch_names[x - 1], image=img)
                self.submenu1.append(action_channel)
                action_channel.connect("activate", self.item_activated, x)
                self.sub1.set_submenu(self.submenu1)

        self.action_channelsmenu.show_all()
        
    def edit_channels(self, *args):
        print("open channels file")
        self.open_message_window("Please restart XAppTrayRadio after changes!")
        Gtk.show_uri(None, f"file://{self.channelsfile}", 2)
        
    def show_help(self, *args):
        about_dialog = Gtk.AboutDialog()
        about_dialog.set_default_size(500, 500)
        about_dialog.set_destroy_with_parent(True)
        about_dialog.set_program_name("XAppTrayRadio")
        about_dialog.set_version("1.0")
        about_dialog.set_authors(["Axel Schneider"])
        artists = ["Michael Webster", 
                                  "Clement Lefebvre", "Stephen Collins", 
                                  "JosephMcc", "Fabio Fantoni", "Leigh Scott", 
                                  "NikoKrause", "Eli Schwartz", 
                                  "Adam DiCarlo", "Emanuele Petriglia"]
        about_dialog.set_artists(artists)
        comment = """thanks to linuxmint developers for XApp StatusIcon
\nTray Icon:\nuse mouse wheel to change volume
use mouse right click to toggle mute"""
        about_dialog.set_comments(comment)
        about_dialog.set_license_type(3)
        about_dialog.run()
        about_dialog.destroy()

    def get_url_from_pls(self, inURL):
        headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.12; rv:55.0) Gecko/20100101 Firefox/55.0',
                    }
        print("pls detecting", inURL)
        url = ""
        if "&" in inURL:
            inURL = inURL.partition("&")[0]
        response = requests.get(inURL, headers = headers)
        print(response.text)
        if "http" in response.text:
            html = response.text.splitlines()
            for line in html:
                if "http" in line:
                    url = f'http{line.split("http")[1]}'
                    break
            print(url)
            return (url)
        else:
           print("badly formatted list") 
           
    def get_url_from_m3u(self, inURL):
        print("checking", inURL)
        response = requests.get(inURL)
        html = response.text.replace("https", "http").splitlines()
        playlist = []

        for line in html:
            if not line.startswith("#") and len(line) > 0 and line.startswith("http"):
                playlist.append(line)

        if len(playlist) > 0:
            print("URL:", playlist[0])
            return(playlist[0])
        else:
            print("error getting stream url")

    def stop_playing(self, *args):
        self.player.set_state(Gst.State.NULL)
        self.is_playing = False
        
    def start_playing(self, *args):
        if self.is_playing:
            self.lbl.set_text("")
            self.stop_playing()
        else:
            self.item_activated(self, self.channel)

    def play_clipboard_url(self, *args):
        c = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        url = c.wait_for_text()
        print(url)
        if url.endswith(".pls"):
            url = self.get_url_from_pls(url)
        if url.endswith(".m3u"):
            url = self.get_url_from_m3u(url)    
        self.play_radio(url)

    def set_volume(self, *args):
        v = float(self.slider.get_value()/100)
        self.player.set_property("volume", v)
        vol_change = f"changed volume to {str(v * 100)[:2]}"
        print(vol_change)
        self.set_tooltip_text(vol_change)

    def handle_close(self, *args):
        self.player.set_state(Gst.State.NULL)
        print("Player stopped", "\nGoodbye ...")
        self.write_settings()
        Gtk.main_quit()

    def play_radio(self, url, *args):
        self.player.set_state(Gst.State.NULL)
        self.player.set_property("uri", url)
        self.player.set_property("buffer-size", 2*1048576) # 2MB
        self.player.set_state(Gst.State.PLAYING)
        self.url = url

    def toggle_mute(self):
        if self.player.get_property("mute") == False:
            self.player.set_property("mute", True)
            print("muted")
            self.set_tooltip_text("muted")
        else:
            self.player.set_property("mute", False)
            print("unmuted")
            self.set_tooltip_text("unmuted")

    def read_settings(self, *args):
        print("reading settings")
        parser = ConfigParser()
        confFile = path.join(self.cwd, "settings.conf")
        if path.exists(confFile):
            parser.read(confFile)            
            self.volume = float(parser.get('Preferences', 'radio_volume'))
            self.url = parser.get('Preferences', 'last_channel')
            self.ch_name = parser.get('Preferences', 'last_name')
            print(f'Volume set to {self.volume}\nplaying last Channel: {self.url}')
            self.slider.set_value(int(self.volume))
            if not self.url == '':
                self.play_radio(self.url)
                self.set_label(self.ch_name)

            
    def write_settings(self):
        print("writing settings")
        confFile = path.join(self.cwd, "settings.conf")
        config = ConfigParser()
        config.add_section('Preferences')
        config.set('Preferences', 'radio_volume', str(self.slider.get_value()))
        config.set('Preferences', 'last_channel', self.url)
        config.set('Preferences', 'last_name', self.ch_name)       
        with open(confFile, 'w') as confFile:
            config.write(confFile)
            
            
win = MainWindow()
print("Welcome to XAppTrayRadio")
win.read_settings()
Gtk.main()
