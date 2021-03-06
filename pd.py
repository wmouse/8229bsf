import sigrokdecode as srd


class SamplerateError(Exception):
    pass


class SignalPolarityError(Exception):
    pass


class Annotation:
    (DV, TW, BIT, KEY) = range(4)


class Pin:
    (SCL, SDO) = range(2)


class Decoder(srd.Decoder):
    api_version = 3
    id = '8229bsf'
    name = '8229BSF'
    longname = '8229BSF serial output interface'
    desc = 'Synchronous, serial bus.'
    license = 'mit'
    inputs = ['logic']
    outputs = ['8229bsf']
    tags = ['Debug/trace']
    channels = (
        {'id': 'scl', 'name': 'SCL', 'desc': 'Clock'},
        {'id': 'sdo', 'name': 'SDO', 'desc': 'Data'},
    )
    options = (
        {'id': 'polarity', 'desc': 'Signal polarity', 'default': 'active-low',
            'values': ('active-low', 'active-high')},
        {'id': 'key_num', 'desc': 'Key number', 'default': 8,
            'values': (8, 16)},
    )
    annotations = (
        ('dv', 'Data valid'),
        ('tw', 'Tw'),
        ('bit', 'Bit'),
        ('key', 'Key press status'),
    )
    annotation_rows = (
        ('fields', 'Fields', (Annotation.DV, Annotation.TW, Annotation.BIT)),
        ('keymsg', 'Key message', (Annotation.KEY,)),
    )

    def __init__(self):
        self.key_num = None
        self.out_ann = None

        self.active_signal = None
        self.passive_signal = None
        self.front_edge = None
        self.back_edge = None

        self.timeout_samples_num = None

        self.dv_block_ss = None
        self.tw_block_ss = None
        self.bt_block_ss = None

    def metadata(self, key, value):
        if key == srd.SRD_CONF_SAMPLERATE:
            self.timeout_samples_num = int(2 * (value / 1000.0))

    def start(self):
        self.out_ann = self.register(srd.OUTPUT_ANN)
        self.key_num = self.options['key_num']

        if self.options['polarity'] == 'active-high':
            self.active_signal = 'h'
            self.passive_signal = 'l'
            self.front_edge = 'r'
            self.back_edge = 'f'
        elif self.options['polarity'] == 'active-low':
            self.active_signal = 'l'
            self.passive_signal = 'h'
            self.front_edge = 'f'
            self.back_edge = 'r'
        else:
            raise SignalPolarityError('Unexpected type of signal polarity')

    def reset(self):
        self.dv_block_ss = None
        self.tw_block_ss = None
        self.bt_block_ss = None

    def decode(self):
        if not self.timeout_samples_num:
            raise SamplerateError('Cannot decode without samplerate.')

        if not self.active_signal or not self.passive_signal or not self.front_edge or not self.back_edge:
            raise SignalPolarityError('Polarity of signal is not set')

        while True:
            self.wait({Pin.SCL: self.passive_signal, Pin.SDO: self.front_edge})
            self.dv_block_ss = self.samplenum

            self.wait({Pin.SCL: self.passive_signal, Pin.SDO: self.back_edge})
            self.put(self.dv_block_ss, self.samplenum, self.out_ann, [Annotation.DV, ['Data valid', 'DV']])
            self.tw_block_ss = self.samplenum

            self.wait([{Pin.SCL: self.front_edge, Pin.SDO: self.passive_signal}, {Pin.SCL: self.front_edge, Pin.SDO: self.front_edge}])
            self.put(self.tw_block_ss, self.samplenum, self.out_ann, [Annotation.TW, ['Tw', 'Tw']])
            self.bt_block_ss = self.samplenum

            keys_pressed = list()

            for i in range(self.key_num):
                (scl, sdo) = self.wait({Pin.SCL: self.back_edge})

                if (sdo == 1 and self.active_signal == 'h') or (sdo == 0 and self.active_signal == 'l'):
                    keys_pressed.append(str(i + 1))
                    sdo = 1
                else:
                    sdo = 0

                self.wait([{Pin.SCL: 'f'}, {'skip': self.timeout_samples_num}])
                self.put(self.bt_block_ss, self.samplenum, self.out_ann, [Annotation.BIT, ['Bit: %d' % sdo, '%d' % sdo]])

                if (self.matched & 0b10) and i != (self.key_num - 1):
                    break

                self.bt_block_ss = self.samplenum
            else:
                key_msg = 'Key: %s' % (','.join(keys_pressed)) if keys_pressed else 'Key unpressed'
                key_msg_short = 'K: %s' % (','.join(keys_pressed)) if keys_pressed else 'KU'

                self.put(self.dv_block_ss, self.samplenum, self.out_ann, [Annotation.KEY, [key_msg, key_msg_short]])
