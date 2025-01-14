#!/usr/bin/env python

from __future__ import print_function
import getopt, os, sys, plistlib, re, shutil, sys, argparse

if sys.stdout.isatty():
    class tc:
        green = '\033[92m'
        yellow = '\033[93m'
        red = '\033[91m'
        grey = '\033[2m'
        cancel = '\033[0m'

else:
    class tc:
        green = ''
        yellow = ''
        red = ''
        grey = ''
        cancel = ''

class Payload():
    def __init__(self, payload_type, payload):
        self.payload_type = payload_type
        self.payload = payload

    def get_ids(self):
        assert('Not implemented')

    def get_all_ids(self):
        return (self.payload_type,) + self.get_ids()

    def __hash__(self):
        return hash(self.get_all_ids())

    def __eq__(self, other):
        return self.get_all_ids() == other.get_all_ids()

    def __ne__(self, other):
        return not(self == other)

    def __repr__(self):
        return self.__str__()

class PayloadSystemPolicyAllFiles(Payload):
    def __init__(self, payload_type, service_type, payload):
        Payload.__init__(self, payload_type, payload)
        self.service_type = service_type
        self.identifier = payload['Identifier']

    def get_ids(self):
        return (self.identifier, self.service_type)

    def __str__(self):
        return '{}/{} ({})'.format(self.payload_type, self.service_type, self.identifier)

class PayloadKEXT(Payload):
    def __init__(self, payload_type, id):
        Payload.__init__(self, payload_type, None)
        self.id = id

    def get_ids(self):
        return (self.id,)

    def __str__(self):
        return '{} ({})'.format(self.payload_type, self.id)

class PayloadSysExt(Payload):
    def __init__(self, payload_type, team_id, bundle_id):
        Payload.__init__(self, payload_type, None)
        self.team_id = team_id
        self.bunle_id = bundle_id

    def get_ids(self):
        return (self.team_id, self.bunle_id)

    def __str__(self):
        return '{} ({}, {})'.format(self.payload_type, self.team_id, self.bunle_id)

class PayloadWebContentFilter(Payload):
    def __init__(self, payload_type, payload):
        Payload.__init__(self, payload_type, payload)
        self.id = payload['FilterDataProviderBundleIdentifier']
        self.properties = {}

        for p in ('FilterDataProviderDesignatedRequirement', 'FilterGrade', 'FilterSockets', 'FilterType', 'PluginBundleID'):
            self.properties[p] = payload[p]

    def get_ids(self):
        return (self.id,)

    def __str__(self):
        return '{} ({})'.format(self.payload_type, self.id)

class PayloadNotifications(Payload):
    def __init__(self, payload_type, payload):
        Payload.__init__(self, payload_type, payload)
        self.id = payload['BundleIdentifier']

    def get_ids(self):
        return (self.id,)

    def __str__(self):
        return '{} ({})'.format(self.payload_type, self.id)

class PayloadOnboardingInfo(Payload):
    def __init__(self, payload_type, payload):
        Payload.__init__(self, payload_type, payload)

    def get_ids(self):
        return ()

    def __str__(self):
        return '{}'.format(self.payload_type)

def print_warning(s):
    print('{}[WARNING]{} {}'.format(tc.yellow, tc.cancel, s))

def print_success(s):
    print('{}[OK]{} {}'.format(tc.green, tc.cancel, s))

def print_error(s):
    print('{}[ERROR]{} {}'.format(tc.red, tc.cancel, s))

def print_debug(s):
    print('{}{}{}'.format(tc.grey, s, tc.cancel))

def read_plist(path):
    print_debug('Reading {}'.format(path))

    if 'load' in plistlib.__all__:
        with open(path, 'rb') as f:
            return plistlib.load(f)
    else:
        return plistlib.readPlist(path)

def get_SystemPolicyAllFiles(definition):
    return PayloadSystemPolicyAllFiles('com.apple.TCC.configuration-profile-policy', 'SystemPolicyAllFiles', {
                        'Allowed': definition['Allowed'],
                        'CodeRequirement': definition['CodeRequirement'],
                        'IdentifierType': definition['IdentifierType'],
                        'Identifier': definition['Identifier'],
                    })

def get_payloads(payload_type, content):
    if payload_type == 'com.apple.TCC.configuration-profile-policy':
        for service_type, definition_array in content['Services'].items():
            for definition in definition_array:
                if service_type == 'SystemPolicyAllFiles':
                    yield get_SystemPolicyAllFiles(definition)
                else:
                    print_warning('Unexpected payload type: {}, {}'.format(payload_type, service_type))
    elif payload_type == 'com.apple.syspolicy.kernel-extension-policy':
        for id in content["AllowedTeamIdentifiers"]:
            yield PayloadKEXT(payload_type, id)
    elif payload_type == 'com.apple.system-extension-policy':
        for team_id, bundle_ids in content['AllowedSystemExtensions'].items():
            for bundle_id in bundle_ids:
                yield PayloadSysExt(payload_type, team_id, bundle_id)
    elif payload_type == 'com.apple.webcontent-filter':
        yield PayloadWebContentFilter(payload_type, {
            'FilterType': content.get('FilterType'),
            'PluginBundleID': content.get('PluginBundleID'),
            'FilterSockets': content.get('FilterSockets'),
            'FilterDataProviderBundleIdentifier': content.get('FilterDataProviderBundleIdentifier'),
            'FilterDataProviderDesignatedRequirement': content.get('FilterDataProviderDesignatedRequirement'),
            'FilterGrade': content.get('FilterGrade'),
        })
    elif payload_type == 'com.apple.notificationsettings':
        for definition in content['NotificationSettings']:
            yield PayloadNotifications(payload_type, definition)
    elif payload_type == 'com.apple.ManagedClient.preferences':
        if 'PayloadContentManagedPreferences' in content and 'com.microsoft.wdav.atp' in content['PayloadContentManagedPreferences']:
            try:
                onboarding_info = content['PayloadContentManagedPreferences']['com.microsoft.wdav.atp']['Forced'][0]['mcx_preference_settings']['OnboardingInfo']
                yield PayloadOnboardingInfo(payload_type, onboarding_info)
            except:
                print_error("Probably malformed onboarding blob")

def parse_profiles(path):
    result = {}
    plist = read_plist(path)

    for level, profiles in plist.items():
        for profile in profiles:

            for item in profile['ProfileItems']:
                payload_type = item['PayloadType']
                content = item['PayloadContent']

                for payload in get_payloads(payload_type, content):
                    if payload in result:
                        result_payloads = result[payload]
                    else:
                        result_payloads = []

                    result_payloads.append({
                        'payload': payload,
                        'path': path,
                        'level': level,
                        'name': profile['ProfileDisplayName'],
                        'time': profile['ProfileInstallDate']
                    })

                    result[payload] = result_payloads

    return result

def parse_expected(path):
    result = []

    for item in read_plist(path)['PayloadContent']:
        payload_type = item['PayloadType']
        payloads = list(get_payloads(payload_type, item))

        if len(payloads) == 0:
            print_warning('Unexpected payload type: {}, {}'.format(payload_type, item))

        result += payloads

    return result

def parse_tcc(path):
    result = {}
    mdm_tcc = '/tmp/MDMOverrides.plist'

    try:
        shutil.copy(path, mdm_tcc)
        os.system('plutil -convert xml1 "{}"'.format(mdm_tcc))
        tcc = read_plist(mdm_tcc)
    except IOError:
        tcc = None
        print_warning('No {} found, is the machine enrolled into MDM?'.format(path))

    if tcc:
        for service in tcc.values():
            if 'kTCCServiceSystemPolicyAllFiles' in service:
                definition = service['kTCCServiceSystemPolicyAllFiles']
                d = get_SystemPolicyAllFiles(definition)
                definition['CodeRequirementData']
                result[d] = {
                    'CodeRequirement': definition['CodeRequirement'],
                    'IdentifierType': definition['IdentifierType'],
                    'Identifier': definition['Identifier'],
                    'Allowed': definition['Allowed'],
                }

    return result

def format_location(profile_data):
    return '{}, profile: "{}", deployed: {}'.format(profile_data['path'], profile_data['name'], profile_data['time'])

def report(path_profiles, path_expected, path_tcc):
    map_profiles = parse_profiles(path_profiles)
    list_expected = parse_expected(path_expected)
    tcc = parse_tcc(path_tcc)

    for expected in list_expected:
        if expected in map_profiles:
            m = map_profiles[expected]

            t = None
            check_tcc = False

            if expected.payload_type == 'com.apple.TCC.configuration-profile-policy' and expected.service_type == 'SystemPolicyAllFiles':
                if tcc and expected in tcc:
                    t = tcc[expected]

                check_tcc = True

            if len(m) == 1:
                if expected.payload == m[0]['payload'].payload:
                    if not check_tcc or t == m[0]['payload'].payload:
                        print_success("Found {} in {}".format(expected, format_location(m[0])))
                    else:
                        print_error("Found {} in {} but not in TCC database".format(expected, format_location(m[0])))
                else:
                    print_error("Found, but does not match expected {} in {}".format(expected, format_location(m[0])))
                    print_debug("    Found: {}".format(m[0]['payload'].payload))
            else:
                print_error("Duplicate definitions, only one of them is active: {}".format(expected))

                n=1
                for d in m:
                    if expected.payload == d['payload'].payload:
                        match_label = '{}[Match]{}'.format(tc.green, tc.cancel)
                    else:
                        match_label = '{}[Mismatch]{}'.format(tc.red, tc.cancel)

                    if check_tcc:
                        if t == d['payload'].payload:
                            tcc_label = ' {}[In TCC]{}'.format(tc.green, tc.cancel)
                        else:
                            tcc_label = ' {}[Not in TCC]{}'.format(tc.red, tc.cancel)
                    else:
                        tcc_label = ''

                    print_debug("    Candidate {}: {} {}{}{}".format(n, format_location(d), tc.cancel, match_label, tcc_label))
                    n += 1
        else:
            print_error("Not provided: {}".format(expected))

    # 'com.apple.ManagedClient.preferences'
    onboarding_infos = []
    for k, v in map_profiles.items():
        if k.payload_type == 'com.apple.ManagedClient.preferences':
            onboarding_infos += v

    if len(onboarding_infos) == 1:
        print_success("Onboarding info found")
    elif len(onboarding_infos) == 0:
        print_error("Onboarding info not found")
    else:
        print_error("Multiple onboarding info found")
        i = 1
        for info in onboarding_infos:
            print_debug("  {}: {}".format(i, info))

parser = argparse.ArgumentParser(description = "Validates MDM profiles for Defender")
parser.add_argument("--template", type=str, help = "Template file from https://github.com/microsoft/mdatp-xplat/blob/master/macos/mobileconfig/combined/mdatp.mobileconfig")
parser.add_argument("--in", type=str, help = "Optional, read exported profiles from it, instead of getting from the system")
parser.add_argument("--tcc", type=str, help = "Optional, read TCC overrides from it, instead of getting from the system")
args = parser.parse_args()

if not args.template:
    args.template = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'mdatp.mobileconfig')

    if not os.path.exists(args.template):
        url = 'https://raw.githubusercontent.com/microsoft/mdatp-xplat/master/macos/mobileconfig/combined/mdatp.mobileconfig'
        args.template = '/tmp/mdatp.mobileconfig'
        print_debug("Downloading template from {}".format(url))      

        try:
            import urllib.request
            print_debug('Using module urllib.request')

            def downloader():
                try:
                    with urllib.request.urlopen(url) as response, open(args.template, 'wb') as out_file:
                        shutil.copyfileobj(response, out_file)
                except:
                    print_warning('Your Python has issues with SSL validation, please fix it. Querying {} with disabled validation.'.format(url))
                    import ssl
                    ssl._create_default_https_context = ssl._create_unverified_context

                    with urllib.request.urlopen(url) as response, open(args.template, 'wb') as out_file:
                        shutil.copyfileobj(response, out_file)

        except:
            import urllib2
            print_debug('Using module urllib2')

            def downloader():
                response = urllib2.urlopen(url)
                with open(args.template, 'wb') as out_file:
                    out_file.write(response.read())

        downloader()

args.template = os.path.abspath(os.path.expanduser(args.template))

in_file = getattr(args, 'in')

if not in_file:
    in_file = '/tmp/profiles.xml'

    if os.path.exists(in_file):
        print_debug("{} already exists, remove it first".format(in_file))
        os.system('sudo rm -f "{}"'.format(in_file))

    print_debug('Running "profiles" command, sudo password may be required...')
    os.system('sudo profiles show -output "{}"'.format(in_file))

in_file = os.path.abspath(os.path.expanduser(in_file))

if not args.tcc:
    args.tcc = '/Library/Application Support/com.apple.TCC/MDMOverrides.plist'

args.tcc = os.path.abspath(os.path.expanduser(args.tcc))

report(in_file, args.template, args.tcc)
