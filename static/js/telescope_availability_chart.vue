<template>
  <div class="telescopeAvailability">
    {{ error }}
    <table class="availability_chart table table-bordered table-condensed" v-show="sortedTelescopes.length">
      <thead class="thead-default">
      <th>Telescope</th>
      <th v-for="(dateLabel, dataLabelIdx) in dateLabels" :key="dataLabelIdx">{{ dateLabel }}</th>
      </thead>
      <tbody class="tbody-default">
      <tr v-for="(telescope, telescopeIdx) in sortedTelescopes" :key="telescopeIdx">
        <td>{{ telescope | readableSiteName}}</td>
        <td 
          v-for="(availabilities, availabilitiesIdx) in availabilityData[telescope]" 
          :class="[availabilityToColor(availabilities[1])]"
          :key="availabilitiesIdx"
        >
          {{ (availabilities[1] * 100).toFixed() }}
        </td>
      </tr>
      </tbody>
    </table>
    <p v-show="!sortedTelescopes.length && !error" class="text-center"><i class="fa fa-spin fa-spinner"></i></p>
  </div>
</template>
<script>
  import _ from 'lodash';
  import $ from 'jquery';

  // import 'eonasdan-bootstrap-datetimepicker';
  // import 'eonasdan-bootstrap-datetimepicker/build/css/bootstrap-datetimepicker.css';

  export default {
    name: 'app',
    data: function(){
      return {
        availabilityData: {},
        minDate:null,
        maxDate:null,
        dateLabels:[],
        sortedTelescopes:[],
        error: ''
      };
    },
    created: function(){
      let that = this;
      let endDate = new Date();
      let startDate = new Date(endDate);
      startDate.setDate(startDate.getDate() - 3);
      startDate.setHours(0);
      startDate.setMinutes(0);
      startDate.setSeconds(0);
      startDate.setMilliseconds(0);
      $.getJSON('/api/telescope_availability/?start=' + startDate.toISOString() + '&end=' + endDate.toISOString(),
        function(data){
          if(data === 'ConnectionError'){
            that.error = 'Unable to retrieve history';
            return;
          }
          that.availabilityData = data;
        }
      );
    },
    methods: {
      availabilityToColor: function(availability){
        if(availability > 0.75) return 'table-success';
        else if (availability > 0.25) return 'table-warning';
        return 'table-danger';
      }
    },
    watch: {
      availabilityData: function () {
        this.minDate = new Date(8640000000000000);
        this.maxDate = new Date(-8640000000000000);
        for (let telescope in this.availabilityData){
          if(this.availabilityData[telescope].length > 0){
            let firstDate = new Date(this.availabilityData[telescope][0][0]);
            if (firstDate < this.minDate){
              this.minDate = firstDate;
            }
            let lastDate = new Date(_.last(this.availabilityData[telescope])[0]);
            if (lastDate > this.maxDate){
              this.maxDate = lastDate;
            }
            this.sortedTelescopes.push(telescope);
          }
        }
        this.sortedTelescopes.sort();
        this.dateLabels = [];
        let currentDate = new Date(this.minDate);
        while(currentDate <= this.maxDate){
          let days_ago = Math.ceil((this.maxDate.getTime() - currentDate.getTime()) / (1000 * 3600 * 24));
          if(days_ago === 0) this.dateLabels.push('Today');
          else if(days_ago === 1) this.dateLabels.push('-' + days_ago + ' day');
          else this.dateLabels.push('-' + days_ago + ' days');
          currentDate.setDate(currentDate.getDate() + 1);
        }
      }
    }
  };
</script>
