# Macht "custom_components" hier zu einem regulaeren (statt einem impliziten
# Namespace-)Package -- ausschliesslich fuer tests/ha/ relevant: ohne das
# gewinnt beim `hass`-Test-Fixture zuverlaessig das von
# pytest-homeassistant-custom-component mitgelieferte eigene
# "testing_config/custom_components" (selbst ein regulaeres Package) den
# Namespace-Merge-Wettlauf, siehe tests/ha/conftest.py::hass_config_dir()
# fuer die dazugehoerige Gegenmassnahme. Ohne Laufzeitwirkung fuer die echte
# Integration.
