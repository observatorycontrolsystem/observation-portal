import moment from 'moment';

function slitWidthToExposureTime(slitWidth){
  // Lamp flats are affected by the slit width, so exposure time needs to scale with it
  if(slitWidth.includes('1.2')){
    return 70;
  }
  else if(slitWidth.includes('1.6')){
    return 50;
  }
  else if(slitWidth.includes('2.0')){
    return 40;
  }
  else if(slitWidth.includes('6.0')){
    return 15;
  }
  return 60;
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
    var m = ra.match('^([0-9]?[0-9])[: ]([0-5]?[0-9][.0-9]*)[: ]?([.0-9]+)?$');
    if (m) {
      var hh = parseInt(m[1], 10);
      var mm = parseFloat(m[2]);
      var ss = m[3] ? parseFloat(m[3]) : 0.0;
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
    var m = dec.match('^([+-])?([0-9]?[0-9])[: ]([0-5]?[0-9][.0-9]*)[: ]?([.0-9]+)?$');
    if (m) {
      var sign = m[1] === '-' ? -1 : 1;
      var dd = parseInt(m[2], 10);
      var mm = parseFloat(m[3]);
      var ss = m[4] ? parseFloat(m[4]) : 0.0;
      if (dd >= 0 && dd <= 90 && mm >= 0 && mm <= 59 && ss >= 0 && ss < 60) {
        dec = (sign * (dd + mm / 60.0 + ss / 3600.0)).toFixed(10);
      }
    }
  }
  return dec;
}

function QueryString() {
  var qString = {};
  var query = window.location.search.substring(1);
  var vars = query.split('&');
  for (var i = 0; i < vars.length; i++) {
    var pair = vars[i].split('=');
    if (typeof qString[pair[0]] === 'undefined') {
      qString[pair[0]] = decodeURIComponent(pair[1]);
    } else if (typeof qString[pair[0]] === 'string') {
      var arr = [qString[pair[0]], decodeURIComponent(pair[1])];
      qString[pair[0]] = arr;
    } else {
      qString[pair[0]].push(decodeURIComponent(pair[1]));
    }
  }
  return qString;
}

function formatDate(date){
  if(date){
    return moment.utc(String(date)).format(datetimeFormat);
  }
}

function julianToModifiedJulian(jd){
  if(jd && jd >= 2400000.5){
    var precision = (jd + "").split(".")[1].length;
    return Number((parseFloat(jd) - 2400000.5).toFixed(precision));
  }
}

var apiFieldToReadable = {
  'group_id': 'Title'
};

function formatField(value){
  if(value in apiFieldToReadable){
    return apiFieldToReadable[value];
  }else{
    var words = value.split('_');
    words = words.map(function(word){
      return word.charAt(0).toUpperCase() + word.substr(1);
    });
    return words.join(' ');
  }
}

var datetimeFormat = 'YYYY-MM-DD HH:mm:ss';

var collapseMixin = {
  watch: {
    parentshow: function(value){
      this.show = value;
    }
  }
};

var siteToColor = {
  'tfn': '#263c6f',
  'elp': '#700000',
  'lsc': '#f04e23',
  'cpt': '#004f00',
  'coj': '#fac900',
  'ogg': '#3366dd',
  'sqa': '#009d00',
  'tlv': '#8150d7'
};

var siteCodeToName = {
  'tfn': 'Teide',
  'elp': 'McDonald',
  'lsc': 'Cerro Tololo',
  'cpt': 'Sutherland',
  'coj': 'Siding Spring',
  'ogg': 'Haleakala',
  'sqa': 'Sedgwick',
  'ngq': 'Ali',
  'tlv': 'Wise'
};

var observatoryCodeToNumber = {
  'doma': '1',
  'domb': '2',
  'domc': '3',
  'clma': '',
  'aqwa': '1',
  'aqwb': '2'
};

var telescopeCodeToName = {
  '1m0a': '1m',
  '0m4a': '0.4m A',
  '0m4b': '0.4m B',
  '0m4c': '0.4m C',
  '2m0a': '2m',
  '0m8a': '0.8m'
};

var colorPalette = [  // useful assigning colors to datasets.
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
  semesterStart, semesterEnd, sexagesimalRaToDecimal, sexagesimalDecToDecimal, QueryString,
  formatDate, formatField, datetimeFormat, collapseMixin, siteToColor, siteCodeToName, slitWidthToExposureTime,
  observatoryCodeToNumber, telescopeCodeToName, colorPalette, julianToModifiedJulian
};
