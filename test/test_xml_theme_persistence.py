#!/usr/bin/env python

"""test_xml_theme_persistence.py

Integration test to verify that theme changes are persisted to the HUD_config.xml file.
This test verifies the complete XML persistence workflow.
"""

import unittest
import tempfile
import os
import xml.dom.minidom
from unittest.mock import patch
import sys

# Add the parent directory to the path to import our modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ThemeManager import ThemeManager
import Configuration


class TestXMLThemePersistence(unittest.TestCase):
    """Test XML persistence of theme changes."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Reset singleton
        if hasattr(ThemeManager, '_instance'):
            ThemeManager._instance = None
        # Reset class variable for clean tests
        ThemeManager.AVAILABLE_QT_THEMES = None
            
        # Create temporary XML file
        self.temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False)
        self.temp_file_path = self.temp_file.name
        
        # Write initial XML content
        initial_xml = '''<?xml version="1.0" ?><FreePokerToolsConfig>
    <general version="83" config_wrap_len="-1" day_start="5" ui_language="en_US" config_difficulty="expert"/>
    <database db_name="test_fpdb" db_server="sqlite" db_type="sqlite" db_selected="True"/>
</FreePokerToolsConfig>'''
        
        self.temp_file.write(initial_xml)
        self.temp_file.close()
        
    def tearDown(self):
        """Clean up after tests."""
        # Reset singleton
        if hasattr(ThemeManager, '_instance'):
            ThemeManager._instance = None
        # Reset class variable
        ThemeManager.AVAILABLE_QT_THEMES = None
            
        # Clean up temp file
        if os.path.exists(self.temp_file_path):
            os.unlink(self.temp_file_path)
    
    def test_theme_persistence_to_xml_file(self):
        """Test that theme changes are persisted to the actual XML file."""
        # Load configuration from our temp file
        config = Configuration.Config(file=self.temp_file_path)
        
        # Initialize ThemeManager
        theme_manager = ThemeManager()
        theme_manager.initialize(config=config)
        
        # Verify initial state (should have defaults)
        self.assertEqual(theme_manager.get_qt_material_theme(), "dark_purple.xml")
        self.assertEqual(theme_manager.get_popup_theme(), "material_dark")
        
        # Change themes
        result = theme_manager.set_global_theme("light_blue.xml", "material_light")
        self.assertTrue(result, "Theme change should succeed")
        
        # Verify the XML file was updated
        with open(self.temp_file_path, 'r') as f:
            xml_content = f.read()
            
        # Parse the XML to verify attributes
        doc = xml.dom.minidom.parseString(xml_content)
        general_elements = doc.getElementsByTagName("general")
        
        self.assertEqual(len(general_elements), 1, "Should have one general element")
        
        general_element = general_elements[0]
        qt_theme_attr = general_element.getAttribute("qt_material_theme")
        popup_theme_attr = general_element.getAttribute("popup_theme")
        
        self.assertEqual(qt_theme_attr, "light_blue.xml", "Qt material theme should be saved in XML")
        self.assertEqual(popup_theme_attr, "material_light", "Popup theme should be saved in XML")
        
        # Verify other attributes are preserved
        self.assertEqual(general_element.getAttribute("version"), "83")
        self.assertEqual(general_element.getAttribute("ui_language"), "en_US")
    
    def test_theme_persistence_reload_from_xml(self):
        """Test that themes are correctly loaded from XML on reload."""
        # First, create XML with theme attributes
        xml_with_themes = '''<?xml version="1.0" ?><FreePokerToolsConfig>
    <general version="83" config_wrap_len="-1" day_start="5" ui_language="en_US" config_difficulty="expert" qt_material_theme="light_amber.xml" popup_theme="classic"/>
    <database db_name="test_fpdb" db_server="sqlite" db_type="sqlite" db_selected="True"/>
</FreePokerToolsConfig>'''
        
        # Write to temp file
        with open(self.temp_file_path, 'w') as f:
            f.write(xml_with_themes)
        
        # Load configuration
        config = Configuration.Config(file=self.temp_file_path)
        
        # Initialize ThemeManager
        theme_manager = ThemeManager()
        theme_manager.initialize(config=config)
        
        # Verify themes were loaded correctly
        self.assertEqual(theme_manager.get_qt_material_theme(), "light_amber.xml")
        self.assertEqual(theme_manager.get_popup_theme(), "classic")
    
    def test_theme_persistence_missing_attributes(self):
        """Test handling when theme attributes are missing from XML."""
        # Use initial XML without theme attributes (setUp created this)
        config = Configuration.Config(file=self.temp_file_path)
        
        # Initialize ThemeManager
        theme_manager = ThemeManager()
        theme_manager.initialize(config=config)
        
        # Should fall back to defaults
        self.assertEqual(theme_manager.get_qt_material_theme(), "dark_purple.xml")
        self.assertEqual(theme_manager.get_popup_theme(), "material_dark")
        
        # Now save themes and verify they're added to XML
        result = theme_manager.set_qt_material_theme("dark_teal.xml")
        self.assertTrue(result, "Theme change should succeed")
        
        # Verify XML was updated with new attributes
        with open(self.temp_file_path, 'r') as f:
            xml_content = f.read()
            
        doc = xml.dom.minidom.parseString(xml_content)
        general_element = doc.getElementsByTagName("general")[0]
        
        self.assertEqual(general_element.getAttribute("qt_material_theme"), "dark_teal.xml")
        self.assertEqual(general_element.getAttribute("popup_theme"), "material_dark")
    
    def test_xml_formatting_preservation(self):
        """Test that XML formatting and other elements are preserved."""
        # Add more complex XML structure
        complex_xml = '''<?xml version="1.0" ?><FreePokerToolsConfig>
    <general version="83" config_wrap_len="-1" day_start="5" ui_language="en_US" config_difficulty="expert"/>
    <site_ids>
        <site_id site="PokerStars" id="2"/>
    </site_ids>
    <database db_name="fpdb" db_server="sqlite" db_type="sqlite"/>
</FreePokerToolsConfig>'''
        
        with open(self.temp_file_path, 'w') as f:
            f.write(complex_xml)
        
        # Load and modify
        config = Configuration.Config(file=self.temp_file_path)
        theme_manager = ThemeManager()
        theme_manager.initialize(config=config)
        
        # Change theme
        theme_manager.set_global_theme("light_pink.xml")
        
        # Parse the result
        with open(self.temp_file_path, 'r') as f:
            xml_content = f.read()
            
        doc = xml.dom.minidom.parseString(xml_content)
        
        # Verify general element has theme attributes
        general_element = doc.getElementsByTagName("general")[0]
        self.assertEqual(general_element.getAttribute("qt_material_theme"), "light_pink.xml")
        
        # Verify other elements are preserved
        site_ids = doc.getElementsByTagName("site_ids")
        self.assertEqual(len(site_ids), 1, "site_ids element should be preserved")
        
        database = doc.getElementsByTagName("database")
        self.assertEqual(len(database), 1, "database element should be preserved")
        
        site_id = doc.getElementsByTagName("site_id")
        self.assertEqual(len(site_id), 1, "site_id element should be preserved")
        self.assertEqual(site_id[0].getAttribute("site"), "PokerStars")


if __name__ == '__main__':
    unittest.main()