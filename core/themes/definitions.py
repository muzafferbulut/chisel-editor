from core.themes.base import BaseTheme


class LightTheme(BaseTheme):
    name = "Light Theme"

    @property
    def palette(self):
        return {
            'background': '#ffffff',
            'background_alt': '#f8f9fa',
            'text': '#333333',
            'primary': '#0078d4',
            'border': '#dee2e6',
            'input_bg': '#ffffff',

            'button_bg': '#f8f9fa',
            'button_hover': '#e2e6ea',
            'button_pressed': '#dae0e5',

            'header_bg': '#f1f3f4',
            'header_text': '#333333',

            'selection_bg': '#e8f0fe',
            'selection_text': '#0078d4'
        }

    @property
    def three_d_background(self):
        return {'top': '#BBE2F1', 'bottom': '#42535C'}

    @property
    def map_style(self):
        return 'osm'


class DarkTheme(BaseTheme):
    name = "Dark Modern"

    @property
    def palette(self):
        return {
            'background': '#2b2b2b',
            'background_alt': '#3c3f41',
            'text': '#e0e0e0',
            'primary': '#4cc2ff',
            'border': '#555555',
            'input_bg': '#3c3f41',

            'button_bg': '#3c3f41',
            'button_hover': '#4e5254',
            'button_pressed': '#5a5e61',

            'header_bg': '#323232',
            'header_text': '#ffffff',

            'selection_bg': '#094771',
            'selection_text': '#ffffff'
        }

    @property
    def three_d_background(self):
        return {'top': '#1e1e1e', 'bottom': '#000000'}

    @property
    def map_style(self):
        return 'carto_dark'


class HighContrastTheme(BaseTheme):
    name = "High Contrast"

    @property
    def palette(self):
        return {
            'background': '#000000',
            'background_alt': '#000000',
            'text': '#ffffff',
            'primary': '#ffff00',
            'border': '#ffffff',
            'input_bg': '#000000',

            'button_bg': '#000000',
            'button_hover': '#333333',
            'button_pressed': '#666666',

            'header_bg': '#000000',
            'header_text': '#ffff00',

            'selection_bg': '#ffff00',
            'selection_text': '#000000'
        }

    @property
    def three_d_background(self):
        return {'top': '#000000', 'bottom': '#000000'}

    @property
    def map_style(self):
        return 'carto_dark'


class OceanicTheme(BaseTheme):
    name = "Oceanic Pro"

    @property
    def palette(self):
        return {
            'background': '#0f172a',      # Koyu Okyanus Mavisi (Slate 900)
            'background_alt': '#1e293b',  # Biraz daha açık (Slate 800)
            'text': '#f1f5f9',            # Kırık Beyaz (Slate 100)
            'primary': '#38bdf8',         # Canlı Gökyüzü Mavisi (Sky 400)
            'border': '#334155',          # Silik Mavi Çerçeve (Slate 700)
            'input_bg': '#1e293b',        # Input alanları

            'button_bg': '#334155',       # Buton zemin
            'button_hover': '#475569',    # Hover durumu
            'button_pressed': '#64748b',  # Tıklama durumu

            'header_bg': '#020617',       # Çok koyu başlık (Slate 950)
            'header_text': '#38bdf8',     # Başlık yazısı

            'selection_bg': '#0ea5e9',    # Seçim rengi (Sky 500)
            'selection_text': '#ffffff'
        }

    @property
    def three_d_background(self):
        return {'top': '#0f172a', 'bottom': '#020617'}

    @property
    def map_style(self):
        return 'carto_dark'


class ForestTheme(BaseTheme):
    name = "Forest Pro"

    @property
    def palette(self):
        return {
            'background': '#1a2421',      # Derin Orman Yeşili
            'background_alt': '#24302c',  # Biraz daha açık yeşil-gri
            'text': '#e8f5e9',            # Açık nane yeşili/beyaz
            'primary': '#66bb6a',         # Canlı Yaprak Yeşili
            'border': '#2e4c36',          # Koyu yosun yeşili çerçeve
            'input_bg': '#24302c',        # Input alanları

            'button_bg': '#2e4c36',       # Buton zemin
            'button_hover': '#3d6648',    # Hover durumu
            'button_pressed': '#4a7a58',  # Tıklama durumu

            'header_bg': '#0f1614',       # Çok koyu başlık
            'header_text': '#66bb6a',     # Başlık yazısı

            'selection_bg': '#43a047',    # Seçim rengi (Doğal Yeşil)
            'selection_text': '#ffffff'
        }

    @property
    def three_d_background(self):
        return {'top': '#1b2e25', 'bottom': '#050a08'}

    @property
    def map_style(self):
        return 'carto_dark'


class MidnightTheme(BaseTheme):
    name = "Midnight Pro"

    @property
    def palette(self):
        return {
            'background': '#0f0c29',      # Derin Gece Mavisi/Moru
            'background_alt': '#1b1638',  # Biraz daha açık morumsu gri
            'text': '#e0c3fc',            # Açık Lavanta (Okunabilirlik için)
            'primary': '#7b2cbf',         # Elektrik Moru (Vurgu rengi)
            'border': '#3c096c',          # Koyu mor çerçeve
            'input_bg': '#241e4d',        # Input alanları

            'button_bg': '#3c096c',       # Buton zemin
            'button_hover': '#5a189a',    # Hover durumu (Daha parlak mor)
            'button_pressed': '#240046',  # Tıklama durumu

            'header_bg': '#050314',       # Simsiyah'a yakın başlık
            'header_text': '#9d4edd',     # Neon mor başlık yazısı

            'selection_bg': '#9d4edd',    # Seçim rengi (Neon Mor)
            'selection_text': '#ffffff'
        }

    @property
    def three_d_background(self):
        return {'top': '#000000', 'bottom': '#240046'}

    @property
    def map_style(self):
        return 'carto_dark'


class SolarTheme(BaseTheme):
    name = "Solar Pro"

    @property
    def palette(self):
        return {
            'background': '#002b36',      # Solarized Base03 (Derin Petrol Yeşili/Mavisi)
            'background_alt': '#073642',  # Solarized Base02
            'text': '#93a1a1',            # Solarized Base1 (Yumuşak Gri)
            'primary': '#b58900',         # Solarized Yellow (Amber/Bal Rengi)
            'border': '#586e75',          # Base01
            'input_bg': '#073642',        # Input alanları

            'button_bg': '#586e75',       # Buton zemin
            'button_hover': '#657b83',    # Hover durumu
            'button_pressed': '#002b36',  # Tıklama durumu

            'header_bg': '#001e26',       # Daha koyu petrol
            'header_text': '#cb4b16',     # Solarized Orange (Vurgu)

            'selection_bg': '#2aa198',    # Solarized Cyan (Seçim Rengi)
            'selection_text': '#ffffff'
        }

    @property
    def three_d_background(self):
        return {'top': '#002b36', 'bottom': '#073642'}

    @property
    def map_style(self):
        return 'carto_dark'
