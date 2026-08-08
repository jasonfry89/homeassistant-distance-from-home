# Distance From Home - Home Assistant integration

Calculates distance and time for locations from home via multiple modes of transportation. 

### Installation 

Install [HACS](https://www.hacs.xyz/)

Navigate to `HACS` in your Home Assistant 

Add https://github.com/jasonfry89/homeassistant-distance-from-home as a [Custom Repository](https://www.hacs.xyz/docs/faq/custom_repositories/) as type `Integration`

Search HACS for `Distance From Home` and click `Download`

Restart Home Assistant

Navigate to `Integrations`

Press `Add integration`

Search for `Distance From Home`

### Developing

Follow the instructions [here](https://developers.home-assistant.io/docs/development_environment/) to setup a local Home Assistant development environment

Modify `$YOUR_HA_DEV_ENV/homeassistant/generated/integrations.json` to include:

```
"distance_from_home": {
  "name": "Distance From Home",
  "integration_type": "service",
  "config_flow": true,
  "iot_class": "cloud_polling"
},
```

Create a symbolic link to this repository:

`ln -s $THIS_REPO/custom_components/distance_from_home $YOUR_HA_DEV_ENV/homeassistant/components/distance_from_home`

This approach allows you to test your code in the development environment and get syntax highlighting