# Custom Themes Usage Guide

This guide explains how to create and use custom themes in fpdb (Free Poker Database).

## Overview

fpdb supports custom themes that allow you to personalize the appearance of the application. The theme system includes:

- **qt_material themes** - Main application interface styling
- **Popup themes** - HUD popup window styling  
- **Custom theme creator** - Built-in tool for creating themes
- **Theme manager** - Centralized theme management

## Getting Started

### Method 1: Using the Built-in Theme Creator (Recommended)

The easiest way to create custom themes is using fpdb's built-in Theme Creator dialog:

1. **Open the Theme Creator**
   - Launch fpdb
   - Navigate to the Themes menu
   - Select "Create Custom Theme"

2. **Configure Your Theme**
   - **Theme Information**: Enter name, description, and author
   - **Base Preset**: Choose "Dark", "Light", or "Custom" as starting point
   - **Colors**: Customize the color palette using the color pickers:
     - **Primary**: Main accent color for buttons and highlights
     - **Secondary**: Secondary accent color
     - **Background**: Main background color
     - **Surface**: Color for cards, dialogs, panels
     - **Text**: Primary text color
     - **Text Secondary**: Secondary/dimmed text color

3. **Preview and Create**
   - Click "Update Preview" to see how colors look
   - Click "Create Theme" to save and install the theme
   - Your theme will be available in the Themes menu

### Method 2: Manual Theme Creation

For advanced users who want more control, you can create theme files manually:

1. **Create Theme Directory**
   ```
   ~/.fpdb/themes/
   ```
   This directory is created automatically when fpdb runs.

2. **Create Theme XML File**
   Create a `.xml` file with the qt_material format:

   ```xml
   <!--?xml version="1.0" encoding="UTF-8"?-->
   <!--
   Custom Theme: Your Theme Name
   Author: Your Name
   Description: Brief description
   -->
   <resources>
     <color name="primaryColor">#3F51B5</color>
     <color name="primaryLightColor">#5C6BC0</color>
     <color name="secondaryColor">#2b2b2b</color>
     <color name="secondaryLightColor">#404040</color>
     <color name="secondaryDarkColor">#1a1a1a</color>
     <color name="primaryTextColor">#ffffff</color>
     <color name="secondaryTextColor">#cccccc</color>
   </resources>
   ```

3. **Save the File**
   Save your theme file as `my_theme.xml` in `~/.fpdb/themes/`

4. **Restart fpdb**
   Your theme will appear in the Themes menu after restarting the application.

## Color Reference

### Required Colors

Your theme XML must include these color definitions:

| Color Name | Purpose | Example |
|------------|---------|---------|
| `primaryColor` | Main accent color, buttons, highlights | `#3F51B5` |
| `primaryLightColor` | Lighter variant of primary color | `#5C6BC0` |
| `secondaryColor` | Background color | `#2b2b2b` |
| `secondaryLightColor` | Lighter background for surfaces | `#404040` |
| `secondaryDarkColor` | Darker background variant | `#1a1a1a` |
| `primaryTextColor` | Main text color | `#ffffff` |
| `secondaryTextColor` | Secondary/dimmed text | `#cccccc` |

### Color Tips

- **Dark themes**: Use dark backgrounds (`#2b2b2b`) with light text (`#ffffff`)
- **Light themes**: Use light backgrounds (`#fafafa`) with dark text (`#212121`)
- **Contrast**: Ensure good contrast between text and background colors
- **Consistency**: Use color variations that work well together
- **Accessibility**: Test with users who have vision differences

## Theme Management

### Installing Themes

1. **Using Theme Creator**: Themes are installed automatically
2. **Manual installation**: 
   - Place `.xml` file in `~/.fpdb/themes/`
   - Restart fpdb
   - Theme appears in Themes menu

### Switching Themes

1. Open fpdb
2. Go to Themes menu
3. Select your desired theme
4. Theme is applied immediately and saved automatically

### Removing Custom Themes

1. **Via Theme Manager**:
   ```python
   from ThemeManager import ThemeManager
   theme_manager = ThemeManager()
   theme_manager.remove_custom_theme("my_theme.xml")
   ```

2. **Manual removal**:
   - Delete the `.xml` file from `~/.fpdb/themes/`
   - Restart fpdb

## Example Themes

### Dark Purple Theme
```xml
<resources>
  <color name="primaryColor">#9C27B0</color>
  <color name="primaryLightColor">#BA68C8</color>
  <color name="secondaryColor">#2b2b2b</color>
  <color name="secondaryLightColor">#404040</color>
  <color name="secondaryDarkColor">#1a1a1a</color>
  <color name="primaryTextColor">#ffffff</color>
  <color name="secondaryTextColor">#cccccc</color>
</resources>
```

### Ocean Blue Theme
```xml
<resources>
  <color name="primaryColor">#0277BD</color>
  <color name="primaryLightColor">#03A9F4</color>
  <color name="secondaryColor">#263238</color>
  <color name="secondaryLightColor">#37474F</color>
  <color name="secondaryDarkColor">#1c2428</color>
  <color name="primaryTextColor">#ffffff</color>
  <color name="secondaryTextColor">#B0BEC5</color>
</resources>
```

### Forest Green Theme
```xml
<resources>
  <color name="primaryColor">#388E3C</color>
  <color name="primaryLightColor">#66BB6A</color>
  <color name="secondaryColor">#1B5E20</color>
  <color name="secondaryLightColor">#2E7D32</color>
  <color name="secondaryDarkColor">#0d2818</color>
  <color name="primaryTextColor">#ffffff</color>
  <color name="secondaryTextColor">#C8E6C9</color>
</resources>
```

## Advanced Customization

### HUD Popup Theme Synchronization

fpdb automatically synchronizes HUD popup themes with your qt_material theme:

- **Dark themes** → `material_dark` popup theme
- **Light themes** → `material_light` popup theme

### Custom Theme Directory

Custom themes are stored in:
- **Linux/Mac**: `~/.fpdb/themes/`
- **Windows**: `%USERPROFILE%/.fpdb/themes/`

### Theme Validation

fpdb validates custom themes on installation:

1. **File format**: Must be valid XML
2. **File extension**: Must end in `.xml`
3. **Root element**: Must be `<resources>` (qt_material format)
4. **Required colors**: Should include all required color definitions

### Programmatic Theme Management

For developers, themes can be managed programmatically:

```python
from ThemeManager import ThemeManager

# Get theme manager instance
tm = ThemeManager()

# List available themes
themes = tm.get_available_qt_themes()

# Set theme
tm.set_global_theme("my_custom_theme.xml")

# Install new theme
tm.install_custom_theme("/path/to/theme.xml", "new_theme.xml")

# Check if theme is custom
is_custom = tm.is_custom_theme("my_theme.xml")

# Remove custom theme
tm.remove_custom_theme("old_theme.xml")
```

## Troubleshooting

### Theme Not Appearing

1. **Check file location**: Ensure `.xml` file is in `~/.fpdb/themes/`
2. **Check file format**: Validate XML syntax
3. **Restart fpdb**: Custom themes are loaded on startup
4. **Check logs**: Look for theme validation errors in fpdb logs

### Colors Not Applied

1. **Check color format**: Use hex colors like `#ffffff`
2. **Check required colors**: Ensure all required colors are defined
3. **Check XML structure**: Verify `<resources>` root element
4. **Test with minimal theme**: Start with basic color set

### Theme Creator Issues

1. **Missing colors**: All color fields must be filled
2. **Invalid theme name**: Avoid special characters in theme names
3. **Permissions**: Ensure write access to `~/.fpdb/themes/` directory

## Best Practices

### Design Guidelines

1. **Consistency**: Use a cohesive color palette
2. **Contrast**: Ensure readability with sufficient contrast
3. **Testing**: Test themes in different lighting conditions
4. **Documentation**: Include author and description in theme files

### File Management

1. **Naming**: Use descriptive filenames (e.g., `dark_ocean.xml`)
2. **Backup**: Keep copies of custom themes
3. **Version control**: Track changes if modifying themes frequently
4. **Sharing**: Use comments in XML for theme information

### Performance

1. **File size**: Keep theme files small (usually < 1KB)
2. **Validation**: Ensure themes validate before installation
3. **Testing**: Test themes before sharing with others

## Support

For issues with custom themes:

1. **Check logs**: fpdb logs contain theme-related error messages
2. **Validate XML**: Use XML validators to check theme file syntax
3. **Community**: Share themes and get help from fpdb community
4. **Documentation**: Refer to fpdb documentation for latest updates

## Conclusion

Custom themes allow you to personalize fpdb to match your preferences and playing environment. Whether using the built-in Theme Creator for simplicity or creating themes manually for full control, you can create professional-looking themes that enhance your poker analysis experience.

Remember to test your themes thoroughly and consider sharing successful themes with the fpdb community!