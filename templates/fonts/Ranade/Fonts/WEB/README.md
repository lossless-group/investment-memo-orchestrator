# Installing Webfonts
Follow these simple Steps.

## 1.
Put `ranade/` Folder into a Folder called `fonts/`.

## 2.
Put `ranade.css` into your `css/` Folder.

## 3. (Optional)
You may adapt the `url('path')` in `ranade.css` depends on your Website Filesystem.

## 4.
Import `ranade.css` at the top of you main Stylesheet.

```
@import url('ranade.css');
```

## 5.
You are now ready to use the following Rules in your CSS to specify each Font Style:
```
font-family: Ranade-Thin;
font-family: Ranade-ThinItalic;
font-family: Ranade-Light;
font-family: Ranade-LightItalic;
font-family: Ranade-Regular;
font-family: Ranade-Italic;
font-family: Ranade-Medium;
font-family: Ranade-MediumItalic;
font-family: Ranade-Bold;
font-family: Ranade-BoldItalic;
font-family: Ranade-Variable;
font-family: Ranade-VariableItalic;

```
## 6. (Optional)
Use `font-variation-settings` rule to controll axes of variable fonts:
wght 700.0

Available axes:
'wght' (range from 100.0 to 700.0

