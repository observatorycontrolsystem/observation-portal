import moment from 'moment';
import _ from 'lodash';
import $ from 'jquery';


function isSoarInstrument(instrumentType) {
  return _.toLower(instrumentType).includes('soar');
}

function lampFlatDefaultExposureTime(slitWidth, instrumentType, readoutMode) {
  // Lamp flats are affected by the slit width, so exposure time needs to scale with it
  readoutMode = _.toLower(readoutMode);
  slitWidth = _.toLower(slitWidth);
  if (isSoarInstrument(instrumentType)) {
    if (readoutMode.includes('400m1')) {
      return 3;
    } else if (readoutMode.includes('400m2')) {
      return 2;
    }
  } else {
    if (slitWidth.includes('1.2')) {
      return 70;
    }
    else if (slitWidth.includes('1.6')) {
      return 50;
    }
    else if (slitWidth.includes('2.0')) {
      return 40;
    }
    else if (slitWidth.includes('6.0')) {
      return 15;
    }
  }
  return 60;
}

function arcDefaultExposureTime(instrumentType) {
  if (isSoarInstrument(instrumentType)) {
    return 0.5;
  } else {
    return 60;
  }
}

function semesterStart(datetime){
  if(datetime.month() < 3 ){
    return datetime.subtract(1, 'years').month(9).date(1);
  }else if(datetime.month() < 9){
    return datetime.month(3).date(1);
  }else{
    return datetime.month(9).date(1);
  }
}

function semesterEnd(datetime){
  if(datetime.month() < 3){
    return datetime.month(3).date(1).subtract(1, 'days');
  }else if(datetime.month() < 9){
    return datetime.month(9).date(1).subtract(1, 'days');
  }else{
    return datetime.add(1, 'years').month(3).date(1).subtract(1, 'days');
  }
}

function sexagesimalRaToDecimal(ra) {
  // algorithm: ra_decimal = 15 * ( hh + mm/60 + ss/(60 * 60) )
  /*                 (    hh     ):(     mm            ):  (   ss  ) */
  if(typeof ra === 'string') {
    let m = ra.match('^([0-9]?[0-9])[: ]([0-5]?[0-9][.0-9]*)[: ]?([.0-9]+)?$');
    if (m) {
      let hh = parseInt(m[1], 10);
      let mm = parseFloat(m[2]);
      let ss = m[3] ? parseFloat(m[3]) : 0.0;
      if (hh >= 0 && hh <= 23 && mm >= 0 && mm < 60 && ss >= 0 && ss < 60) {
        ra = (15.0 * (hh + mm / 60.0 + ss / (3600.0))).toFixed(10);
      }
    }
  }
  return ra;
}

function sexagesimalDecToDecimal(dec){
  // algorithm: dec_decimal = sign * ( dd + mm/60 + ss/(60 * 60) )
  /*                  ( +/-   ) (    dd     ):(     mm            ): (   ss   ) */
  if(typeof dec === 'string') {
    let m = dec.match('^([+-])?([0-9]?[0-9])[: ]([0-5]?[0-9][.0-9]*)[: ]?([.0-9]+)?$');
    if (m) {
      let sign = m[1] === '-' ? -1 : 1;
      let dd = parseInt(m[2], 10);
      let mm = parseFloat(m[3]);
      let ss = m[4] ? parseFloat(m[4]) : 0.0;
      if (dd >= 0 && dd <= 90 && mm >= 0 && mm <= 59 && ss >= 0 && ss < 60) {
        dec = (sign * (dd + mm / 60.0 + ss / 3600.0)).toFixed(10);
      }
    }
  }
  return dec;
}

function decimalRaToSexigesimal(deg){
  let rs = 1;
  let ra = deg;
  if(deg < 0){
    rs = -1;
    ra = Math.abs(deg);
  }
  let raH = Math.floor(ra / 15)
  let raM = Math.floor(((ra / 15) - raH) * 60)
  let raS = ((((ra / 15 ) - raH ) * 60) - raM) * 60
  return {
    'h': raH * rs,
    'm': raM,
    's': raS,
    'str': (rs > 0 ? '' : '-') + zPadFloat(raH) + ':' + zPadFloat(raM) + ':' + zPadFloat(raS)
  }
}

function decimalDecToSexigesimal(deg){
  let ds = 1;
  let dec = deg;
  if(deg < 0){
    ds = -1;
    dec = Math.abs(deg);
  }
  let decf = Math.floor(dec)
  let decM = Math.abs(Math.floor((dec - decf) * 60));
  let decS = (Math.abs((dec - decf) * 60) - decM) * 60
  return {
    'deg': decf * ds,
    'm': decM,
    's': decS,
    'str': (ds > 0 ? '' : '-') + zPadFloat(decf) + ':' + zPadFloat(decM) + ':' + zPadFloat(decS)
  }
}

function QueryString() {
  let qString = {};
  let query = window.location.search.substring(1);
  let vars = query.split('&');
  for (let i = 0; i < vars.length; i++) {
    let pair = vars[i].split('=');
    if (typeof qString[pair[0]] === 'undefined') {
      qString[pair[0]] = decodeURIComponent(pair[1]);
    } else if (typeof qString[pair[0]] === 'string') {
      let arr = [qString[pair[0]], decodeURIComponent(pair[1])];
      qString[pair[0]] = arr;
    } else {
      qString[pair[0]].push(decodeURIComponent(pair[1]));
    }
  }
  return qString;
}

 function zPadFloat(num){
  return num.toLocaleString(undefined, {'minimumIntegerDigits': 2, 'maximumFractionDigits': 4})
}

function formatDate(date){
  if(date){
    return moment.utc(String(date)).format(datetimeFormat);
  }
}

function julianToModifiedJulian(jd){
  if(jd && jd >= 2400000.5){
    let precision = (jd + "").split(".")[1].length;
    return Number((parseFloat(jd) - 2400000.5).toFixed(precision));
  }
}

let apiFieldToReadable = {
  group_id: {
    humanReadable: 'Title',
    description: ''
  },
  rotator_angle: {
    humanReadable: 'Rotator Angle',
    description: 'Position angle of the slit in degrees east of north.'
  },
  acquire_radius: {
    humanReadable: 'Acquire Radius',
    description: 'The radius (in arcseconds) within which to search for the brightest object.'
  },
  ra: {
    humanReadable: 'RA',
    description: ''
  }
};

function formatField(value){
  if (value in apiFieldToReadable) {
    return apiFieldToReadable[value]['humanReadable'];
  } else {
    let words = value.split('_');
    words = words.map(function(word){
      return word.charAt(0).toUpperCase() + word.substr(1);
    });
    return words.join(' ');
  }
}

function getFieldDescription(value) {
  if (value in apiFieldToReadable) {
    return apiFieldToReadable[value]['description'];
  } else {
    return '';
  }
}

function formatJson(dict){
  let stringVal = '';
  for(let key in dict){
    if (!_.isEmpty(dict[key]) || _.isNumber(dict[key])) {
      if (!_.isEmpty(stringVal)) {
        stringVal += ', ';
      }
      stringVal += key + ': ' + dict[key];
    }
  }
  return stringVal;
}

function formatValue(value){
  if (_.isObject(value) && !_.isArray(value)){
    return formatJson(value);
  }
  else if (_.isNumber(value) && !_.isInteger(value) && !isNaN(value)){
    return Number(value).toFixed(4);
  }
  return value;
}

function extractTopLevelErrors(errors) {
  let topLevelErrors = [];
  if (_.isString(errors)) {
    // The error will be a string if a validate_xxx method of the parent serializer
    // returned an error, for example the validate_instrument_configs method on the 
    // ConfigurationSerializer. These should be displayed at the top of a section.
    topLevelErrors = _.concat(topLevelErrors, [errors]);
  }
  if (errors.non_field_errors) {
    topLevelErrors = _.concat(topLevelErrors, errors.non_field_errors);
  }
  return topLevelErrors;
}

function getCookie(name) {
  var cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    var cookies = document.cookie.split(';');
    for (var i = 0; i < cookies.length; i++) {
      var cookie = $.trim(cookies[i]);
      // Does this cookie string begin with the name we want?
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

function csrfSafeMethod(method) {
  // these HTTP methods do not require CSRF protection
  return (/^(GET|HEAD|OPTIONS|TRACE)$/.test(method));
}

function addCsrfProtection(settings, xhr) {
  // Give ajax POSTs CSRF protection
  if (!csrfSafeMethod(settings.type) && !this.crossDomain) {
    var csrftoken = getCookie('csrftoken');
    xhr.setRequestHeader('X-CSRFToken', csrftoken);
  }
}

let datetimeFormat = 'YYYY-MM-DD HH:mm:ss';

const tooltipConfig = {
  delay: {
    show: 500, 
    hide: 100
  }, 
  trigger: 'hover'
};

let collapseMixin = {
  watch: {
    parentshow: function(value){
      this.show = value;
    }
  }
};

let siteToColor = {
  'tfn': '#263c6f',  // dark blue
  'elp': '#700000',  // dark red
  'lsc': '#f04e23',  // red-orange
  'cpt': '#004f00',  // dark green
  'coj': '#fac900',  // golden-yellow
  'ogg': '#3366dd',  // sky blue
  'sqa': '#009d00',  // green
  'tlv': '#8150d7',  // purple
  'sor': '#7EF5C9',  // sea green
  'ngq': '#FA5DEB',  // magenta
};

let siteCodeToName = {
  'tfn': 'Teide',
  'elp': 'McDonald',
  'lsc': 'Cerro Tololo',
  'cpt': 'Sutherland',
  'coj': 'Siding Spring',
  'ogg': 'Haleakala',
  'sqa': 'Sedgwick',
  'ngq': 'Ali',
  'sor': 'Cerro Pachón',
  'tlv': 'Wise'
};

let observatoryCodeToNumber = {
  'doma': '1',
  'domb': '2',
  'domc': '3',
  'clma': '',
  'aqwa': '1',
  'aqwb': '2'
};

let telescopeCodeToName = {
  '1m0a': '1m',
  '0m4a': '0.4m A',
  '0m4b': '0.4m B',
  '0m4c': '0.4m C',
  '2m0a': '2m',
  '4m0a': '4m',
  '0m8a': '0.8m'
};

let colorPalette = [  // useful assigning colors to datasets.
  '#3366CC', '#DC3912', '#FF9900', '#109618', '#990099', '#3B3EAC', '#0099C6', '#DD4477',
  '#66AA00', '#B82E2E', '#316395', '#994499', '#22AA99', '#AAAA11', '#6633CC', '#E67300',
  '#8B0707', '#329262', '#5574A6', '#3B3EAC', '#FFFF00', '#1CE6FF', '#FF34FF', '#FF4A46',
  '#008941', '#006FA6', '#A30059', '#FFDBE5', '#7A4900', '#0000A6', '#63FFAC', '#B79762',
  '#004D43', '#8FB0FF', '#997D87', '#5A0007', '#809693', '#FEFFE6', '#1B4400', '#4FC601',
  '#61615A', '#BA0900', '#6B7900', '#00C2A0', '#FFAA92', '#FF90C9', '#B903AA', '#D16100',
  '#DDEFFF', '#000035', '#7B4F4B', '#A1C299', '#300018', '#0AA6D8', '#013349', '#00846F',
  '#372101', '#FFB500', '#C2FFED', '#A079BF', '#CC0744', '#C0B9B2', '#C2FF99', '#001E09',
  '#00489C', '#6F0062', '#0CBD66', '#EEC3FF', '#456D75', '#B77B68', '#7A87A1', '#788D66',
  '#885578', '#FAD09F', '#FF8A9A', '#D157A0', '#BEC459', '#456648', '#0086ED', '#886F4C',
  '#34362D', '#B4A8BD', '#00A6AA', '#452C2C', '#636375', '#A3C8C9', '#FF913F', '#938A81',
  '#575329', '#00FECF', '#B05B6F', '#8CD0FF', '#3B9700', '#04F757', '#C8A1A1', '#1E6E00',
  '#7900D7', '#A77500', '#6367A9', '#A05837', '#6B002C', '#772600', '#D790FF', '#9B9700',
  '#549E79', '#FFF69F', '#201625', '#72418F', '#BC23FF', '#99ADC0', '#3A2465', '#922329',
  '#5B4534', '#FDE8DC', '#404E55', '#0089A3', '#CB7E98', '#A4E804', '#324E72', '#6A3A4C',
  '#3B5DFF', '#4A3B53', '#FF2F80'
];

export {
  semesterStart, semesterEnd, sexagesimalRaToDecimal, sexagesimalDecToDecimal, QueryString, formatJson, formatValue,
  formatDate, formatField, datetimeFormat, collapseMixin, siteToColor, siteCodeToName, arcDefaultExposureTime, 
  lampFlatDefaultExposureTime, observatoryCodeToNumber, telescopeCodeToName, colorPalette, julianToModifiedJulian, 
  getFieldDescription, decimalRaToSexigesimal, decimalDecToSexigesimal, tooltipConfig, addCsrfProtection,
  extractTopLevelErrors
};
